"""Review probes, not production fixes. Run with the review venv from any directory."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'platform/backend'))
from synthetic_platform.spec import SyntheticDataSpec
from synthetic_platform.pipeline import run
from synthetic_platform.validator import validate
from synthetic_platform.engines.base import get_engine
from synthetic_platform.profile import profile_csv
from synthetic_platform.suggest import suggest_for_table, apply_suggestions, prepare_source
from synthetic_platform.derive import apply_derived

results = {}
def spec(tables, **kw):
    return SyntheticDataSpec.model_validate(dict(name='review_probe', mode='schema_rules',
        purpose='software_testing', engine='rules', tables=tables, **kw))
def constant(name, value, **kw):
    return dict(name=name, type='integer', role='constant', constant_value=value, **kw)

# A real declared formula is changed by derived-column clipping, uncounted as repair.
s = spec([dict(name='t', rows=3, columns=[constant('x', 10),
    dict(name='y', type='integer', role='derived', maximum=5,
         formula={'op':'mul', 'args':[{'col':'x'}, {'const':2}]})])])
r = run(s)
results['derived_clipping'] = dict(values=r['frames']['t'].to_dict('list'),
    repairs=r['report']['tables'][0]['repairs'], summary=r['report']['summary'])

# The schema says non-null, but no final schema check enforces it.
s = spec([dict(name='t', rows=3, columns=[dict(name='x', type='integer', role='empty', nullable=False)])])
r = run(s)
results['nonnullable_empty'] = dict(nulls=int(r['frames']['t']['x'].isna().sum()), summary=r['report']['summary'])

original = json.loads((ROOT/'platform/backend/specs/employee_relational.json').read_text())
s = SyntheticDataSpec.model_validate(original)
r = run(s)
assignments = r['frames']['project_assignments']
results['employee_example'] = dict(rows={k:len(v) for k,v in r['frames'].items()},
    duplicate_employee_project_pairs=int(assignments.duplicated(['employee_id','project_id']).sum()),
    integrity=r['report']['evaluation']['referential_integrity'])

# In a junction table, only the first incoming relationship controls counts.
s.relationships[2].cardinality = 'one_to_one'
s.relationships[2].child_count_min = 1
s.relationships[2].child_count_max = 1
r = run(s)
results['secondary_one_to_one'] = dict(validation_ok=validate(s,get_engine('relational_rules').capabilities()).ok,
    max_children=int(r['frames']['project_assignments'].groupby('project_id').size().max()),
    summary=r['report']['summary'])

# FK assignments can subsequently be overwritten by derived formulas.
s = SyntheticDataSpec.model_validate(original)
c = s.table('attendance').column('employee_id')
from synthetic_platform.spec import SemanticRole
c.role = SemanticRole.DERIVED
from synthetic_platform.spec import Expr
c.formula = Expr(const='NONEXISTENT')
r = run(s)
results['derived_foreign_key'] = dict(integrity=r['report']['evaluation']['referential_integrity'][0],
    summary=r['report']['summary'])

# Observe what the engine actually receives before predictive_utility splits.
source = pd.DataFrame({'x':range(100), 'target':[i%2 for i in range(100)]})
s = SyntheticDataSpec.model_validate(dict(name='leakage', mode='learned_table', purpose='ml_development',
    engine='independent', tables=[dict(name='t', rows=100, source={'kind':'public_records'},
        columns=[dict(name='x',type='number',role='learned'),dict(name='target',type='boolean',role='learned')])],
    evaluation=dict(checks=['predictive_utility'],target='target',task='classification')))
from synthetic_platform.engines.learned import IndependentEngine
original_generate = IndependentEngine.generate
seen = []
def spy(self, spec, table, rows, source=None):
    seen.extend(source.index.tolist())
    return original_generate(self,spec,table,rows,source)
with patch.object(IndependentEngine, 'generate', spy):
    r = run(s, sources={'t':source})
from sklearn.model_selection import train_test_split
_, test = train_test_split(source,test_size=.25,random_state=s.seed,stratify=source.target)
results['utility_leakage'] = dict(engine_source_rows=len(seen),test_rows=len(test),
    test_rows_seen_by_engine=len(set(test.index)&set(seen)))

# User-controlled table names become filesystem paths. Confine proof to a temp dir.
from synthetic_platform import api
with tempfile.TemporaryDirectory(prefix='synthetic-review-') as tmp:
    storage = Path(tmp)/'storage'
    storage.mkdir()
    s = spec([dict(name='../escaped', rows=1,columns=[constant('x',1)])])
    api.JOBS['probe'] = {'id':'probe'}
    with patch.object(api,'STORAGE',storage):
        api._run_job('probe',s,None,None)
    results['artifact_path_escape'] = dict(status=api.JOBS['probe']['status'],
        outside_job_directory=(storage/'escaped.csv').exists())
    del api.JOBS['probe']

# Temporal rewrite round-trip under nonzero local offset.
source = pd.DataFrame({'stamp':['2026-01-05T05:00:00+00:00']})
from synthetic_platform.spec import Table
t = Table.model_validate(dict(name='t',columns=[dict(name='stamp',type='timestamp',role='learned')]))
rewrites = suggest_for_table(t,get_engine('arf').capabilities(),3,source)
t = apply_suggestions(t,rewrites)
prepared = prepare_source(source,t)
from synthetic_platform.engines.base import apply_identifiers_and_constants
prepared = apply_identifiers_and_constants(prepared,t,2026)
rebuilt,_ = apply_derived(prepared,t)
results['timezone_roundtrip'] = dict(original=str(source.stamp.iloc[0]),rebuilt=str(rebuilt.stamp.iloc[0]))

# Local aggregate inspection only; no source records are copied into this report.
attendance = pd.read_csv('/home/administrator/Documents/Attendance.csv',low_memory=False)
t,p = profile_csv(attendance,'attendance',tz_offset_hours=0)
s = SyntheticDataSpec(name='attendance', mode='learned_table',purpose='ml_development',engine='arf',tables=[t])
v = validate(s,get_engine('arf').capabilities())
start = pd.to_datetime(attendance.attendance_time_in,format='mixed',utc=True)
end = pd.to_datetime(attendance.attendance_time_out,format='mixed',utc=True)
hours = (end-start).dt.total_seconds()/3600
results['attendance_upload'] = dict(rows=len(attendance),columns=len(attendance.columns),
    employees=int(attendance.attendance_user_id.nunique()),missing_timeout=int(end.isna().sum()),
    negative_duration=int((hours<0).sum()),over_24_hours=int((hours>24).sum()),
    validation=v.as_dict(),derived_candidates=[n for n in p['notes'] if n.get('kind')=='derived_candidate' and n.get('applied')])

out = Path(__file__).with_name('probe_results.json')
out.write_text(json.dumps(results,indent=2,default=str)+'\n')
print(json.dumps(results,indent=2,default=str))
