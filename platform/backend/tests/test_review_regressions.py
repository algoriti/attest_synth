"""Behavioural regressions for the September implementation review."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from synthetic_platform.spec import SyntheticDataSpec, Expr, SemanticRole, Table
from synthetic_platform.pipeline import run, PipelineError
from synthetic_platform.validator import validate
from synthetic_platform.engines.base import get_engine, apply_identifiers_and_constants
from synthetic_platform.derive import DerivationError, apply_derived
from synthetic_platform.suggest import suggest_for_table, apply_suggestions, prepare_source


def simple(columns, **table):
    return SyntheticDataSpec.model_validate(dict(name='test',mode='schema_rules',purpose='software_testing',engine='rules',
        tables=[dict(name='records',rows=3,columns=columns,**table)]))


def employee():
    return SyntheticDataSpec.model_validate(json.loads((Path(__file__).parents[1]/'specs/employee_relational.json').read_text()))


@pytest.mark.parametrize('name',['../escaped','/tmp/absolute','a/b','a\\b','.','unsafe.csv'])
def test_unsafe_table_names_rejected(name):
    s=simple([dict(name='x',type='integer',role='constant',constant_value=1)])
    s.tables[0].name=name
    with pytest.raises(PipelineError):run(s)


def test_artifact_storage_containment(tmp_path,monkeypatch):
    from synthetic_platform import api
    from fastapi import HTTPException
    monkeypatch.setattr(api,'STORAGE',tmp_path)
    with pytest.raises(HTTPException):api.artifact_path('job','../evil.csv')
    with pytest.raises(HTTPException):api.artifact_path('../job','file.csv')
    assert api.artifact_path('job','records.csv')==tmp_path/'job'/'records.csv'


def test_derived_bounds_not_silently_clipped():
    s=simple([dict(name='x',type='integer',role='constant',constant_value=10),dict(name='y',type='integer',role='derived',maximum=5,formula={'op':'mul','args':[{'col':'x'},{'const':2}]})])
    with pytest.raises(DerivationError,match='no silent repair'):run(s)


def test_nonnullable_empty_fails_final_status():
    s=simple([dict(name='x',type='integer',role='empty',nullable=False)])
    assert not run(s)['report']['summary']['all_constraints_passed']


def test_derived_foreign_key_rejected():
    s=employee();c=s.table('attendance').column('employee_id');c.role=SemanticRole.DERIVED;c.formula=Expr(const='missing')
    with pytest.raises(PipelineError):run(s)


def test_self_referencing_formula_rejected():
    s=simple([dict(name='x',type='integer',role='derived',formula={'col':'x'})])
    assert not validate(s).ok


@pytest.mark.parametrize('seed',[2,17,2026])
def test_junction_both_bounds_and_unique_pairs(seed):
    s=employee();s.seed=seed;s.relationships[2].child_count_min=3;s.relationships[2].child_count_max=12
    result=run(s);f=result['frames']['project_assignments']
    assert not f.duplicated(['employee_id','project_id']).any()
    assert f.groupby('project_id').size().between(3,12).all()
    assert f.groupby('employee_id').size().between(1,4).all()
    assert result['report']['summary']['all_constraints_passed']


def test_infeasible_secondary_one_to_one_rejected():
    s=employee();s.relationships[2].cardinality='one_to_one'
    with pytest.raises(PipelineError) as rejected:
        run(s)
    assert any(
        finding['code'] in {'infeasible_junction_bounds','infeasible_junction_rows'}
        for finding in rejected.value.findings
    )


def test_infeasible_explicit_child_rows_rejected_during_validation():
    s=employee();s.tables=[s.table('employees'),s.table('attendance')];s.relationships=s.relationships[:1]
    s.table('employees').rows=100
    s.table('attendance').rows=1000
    s.relationships[0].child_count_min=1;s.relationships[0].child_count_max=5
    result=validate(s)
    assert not result.ok
    finding=next(f for f in result.errors if f.code=='infeasible_child_rows')
    assert '1,000 rows' in finding.message
    assert '100..500' in finding.message
    assert 'leave it blank' in finding.message


def test_explicit_child_rows_inside_relationship_bounds_validate_and_generate():
    s=employee();s.tables=[s.table('employees'),s.table('attendance')];s.relationships=s.relationships[:1]
    s.table('attendance').rows=125
    s.relationships[0].child_count_min=1;s.relationships[0].child_count_max=5
    s.table('attendance').column('employee_id').role=SemanticRole.FOREIGN_KEY
    s.table('attendance').column('employee_id').rule=None
    assert validate(s).ok
    result=run(s)
    assert len(result['frames']['attendance'])==125
    assert result['frames']['attendance'].employee_id.isin(result['frames']['employees'].employee_id).all()


def test_unowned_foreign_key_rejected():
    s=simple([dict(name='owner_id',type='integer',role='foreign_key')])
    result=validate(s)
    assert not result.ok
    assert any(f.code=='unowned_foreign_key' for f in result.errors)


def test_optional_relationship_explicit_nulls():
    s=employee();s.tables=[s.table('employees'),s.table('attendance')];s.relationships=s.relationships[:1]
    rel=s.relationships[0];rel.optional=True;rel.null_fraction=.1;s.table('attendance').column('employee_id').nullable=True
    r=run(s);assert r['frames']['attendance'].employee_id.isna().any()
    assert r['report']['summary']['all_constraints_passed']


def test_zero_children_supported():
    s=employee();s.tables=[s.table('employees'),s.table('attendance')];s.relationships=s.relationships[:1]
    s.relationships[0].child_count_min=0;s.relationships[0].child_count_max=0
    r=run(s);assert len(r['frames']['attendance'])==0
    assert r['report']['summary']['all_constraints_passed']


@pytest.mark.parametrize('stamp,offset',[('2026-01-05T05:00:00Z',3),('2026-01-04T23:00:00Z',3),('2026-01-06T03:00:00Z',-5)])
def test_timezone_rewrite_roundtrip(stamp,offset):
    frame=pd.DataFrame({'stamp':[stamp]})
    t=Table.model_validate(dict(name='t',columns=[dict(name='stamp',type='timestamp',role='learned')]))
    t=apply_suggestions(t,suggest_for_table(t,get_engine('arf').capabilities(),offset,frame))
    result,_=apply_derived(apply_identifiers_and_constants(prepare_source(frame,t),t,2026),t)
    assert pd.Timestamp(result.stamp.iloc[0])==pd.Timestamp(stamp)


def test_generator_never_sees_holdout(monkeypatch):
    from synthetic_platform.engines.learned import IndependentEngine
    from synthetic_platform.splitting import split_source
    frame=pd.DataFrame({'x':np.arange(120), 'target':np.arange(120)%2})
    s=SyntheticDataSpec.model_validate(dict(name='t',mode='learned_table',purpose='ml_development',engine='independent',
      tables=[dict(name='t',rows=100,source={'kind':'public_records'},columns=[dict(name='x',type='number',role='learned'),dict(name='target',type='integer',role='learned')])],
      evaluation=dict(checks=['predictive_utility'],target='target',task='classification')))
    train,test,_=split_source(frame,s.evaluation,s.seed)
    original=IndependentEngine.generate
    def spy(self,spec,table,rows,source=None):
        assert set(source.index)==set(train.index)
        assert not set(source.index)&set(test.index)
        return original(self,spec,table,rows,source)
    monkeypatch.setattr(IndependentEngine,'generate',spy)
    result=run(s,sources={'t':frame})
    assert result['report']['evaluation']['split']['test_rows']==30
    assert 'average_precision' in result['report']['evaluation']['predictive_utility']['trained_on_synthetic']


def test_group_and_time_splits():
    from synthetic_platform.splitting import split_source
    from synthetic_platform.spec import Evaluation
    frame=pd.DataFrame({'entity':np.repeat(np.arange(12),5),'time':pd.date_range('2026-01-01',periods=60),'target':np.arange(60)})
    a,b,_=split_source(frame,Evaluation(target='target',split='group',split_column='entity'),42)
    assert not set(a.entity)&set(b.entity)
    a,b,_=split_source(frame,Evaluation(target='target',split='time',split_column='time'),42)
    assert a.time.max()<b.time.min()


def test_arf_reserved_column_names():
    rng=np.random.default_rng(42)
    frame=pd.DataFrame({name:rng.normal(size=120) for name in ('value','tree','nodeid')})
    s=SyntheticDataSpec.model_validate(dict(name='t',mode='learned_table',purpose='software_testing',engine='arf',
      tables=[dict(name='t',rows=30,source={'kind':'public_records'},columns=[dict(name=n,type='number',role='learned') for n in frame])]))
    result=run(s,sources={'t':frame})
    assert list(result['frames']['t'])==list(frame)
    assert len(result['frames']['t'])==30


@pytest.mark.parametrize('name',['retail_relational','education_relational'])
@pytest.mark.parametrize('seed',[11,29,47])
def test_cross_domain_relational_examples(name,seed):
    s=SyntheticDataSpec.model_validate_json((Path(__file__).parents[1]/f'specs/{name}.json').read_text())
    s.seed=seed;r=run(s)
    assert r['report']['summary']['all_constraints_passed']
    assert r['report']['evaluation']['aggregates']
    if name=='retail_relational':
        expected=r['frames']['order_lines'].groupby('customer_id').line_total.sum()
        actual=r['frames']['customers'].set_index('customer_id').total_spend
        assert np.allclose(actual,expected.reindex(actual.index,fill_value=0))
    else:
        expected=r['frames']['enrolments'].groupby('student_id').size()
        actual=r['frames']['students'].set_index('student_id').course_count
        assert actual.equals(expected.reindex(actual.index,fill_value=0).rename('course_count'))


def test_cross_table_failure_reaches_summary():
    from synthetic_platform.spec import CrossTableConstraint
    s=employee()
    s.table('employees').columns.append(__import__('synthetic_platform.spec',fromlist=['Column']).Column(name='limit',type='number',role='constant',constant_value=1))
    s.cross_table_constraints=[CrossTableConstraint(parent_table='employees',child_table='attendance',child_key='employee_id',parent_column='limit',child_column='shift_hours',operator='less_or_equal')]
    r=run(s)
    assert not r['report']['summary']['all_constraints_passed']
    assert r['report']['evaluation']['cross_table_checks'][0]['failing_rows']>0


def test_hosted_assistant_never_confirms_model_claims(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    seen={}
    proposal=json.loads((Path(__file__).parents[1]/'specs/retail_orders.json').read_text())
    def fake_open(request,timeout):
        seen.update(json.loads(request.data))
        return BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode())
    monkeypatch.setattr(assistant.urllib.request,'urlopen',fake_open)
    result=assistant.propose('Create a small retail dataset.')
    assert len(seen['messages'])==2
    assert 'upload_id' not in seen
    assert all(c['provenance']['origin']=='assistant_proposed' and not c['provenance']['confirmed'] for t in result['spec']['tables'] for c in t['columns'])


def test_hosted_assistant_repairs_bad_json_once(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    proposal=json.loads((Path(__file__).parents[1]/'specs/retail_orders.json').read_text())
    responses=iter([
        b'{"choices":[{"message":{"content":"not JSON"}}]}',
        json.dumps({'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode(),
    ])
    requests=[]
    def fake_open(request,timeout):
        requests.append(json.loads(request.data))
        return BytesIO(next(responses))
    monkeypatch.setattr(assistant.urllib.request,'urlopen',fake_open)
    result=assistant.propose('Create a teaching dataset.')
    assert result['review']['correction_attempted']
    assert len(requests)==2
    assert len(requests[1]['messages'])==4


def test_hosted_assistant_reports_failure_after_one_bad_json_repair(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    monkeypatch.setattr(assistant.urllib.request,'urlopen',lambda *a,**kw:BytesIO(b'{"choices":[{"message":{"content":"not JSON"}}]}'))
    with pytest.raises(ValueError,match='after one correction attempt.*Invalid JSON'):
        assistant.propose('Create a teaching dataset.')


def test_hosted_assistant_preserves_explicit_rows_and_omits_fake_period_summary(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    proposal={
        'name':'employee_activity','mode':'relational_rules','purpose':'ml_development','engine':'relational_rules',
        'tables':[
            {'name':'employees','rows':100,'primary_key':'employee_id','columns':[
                {'name':'employee_id','type':'string','role':'identifier'}]},
            {'name':'attendance','rows':None,'primary_key':'attendance_id','columns':[
                {'name':'attendance_id','type':'uuid','role':'identifier'},
                {'name':'employee_id','type':'string','role':'foreign_key'},
                {'name':'status','type':'category','role':'rule','rule':{'kind':'choice','values':['present','absent']}}]},
            {'name':'monthly_performance_summaries','rows':100,'primary_key':'summary_id','columns':[
                {'name':'summary_id','type':'uuid','role':'identifier'},
                {'name':'employee_id','type':'string','role':'foreign_key'},
                {'name':'attendance_rate','type':'number','role':'rule','rule':{'kind':'number_range','start':0,'end':1}}]},
        ],
        'relationships':[
            {'parent_table':'employees','parent_key':'employee_id','child_table':'attendance','child_key':'employee_id','child_count_min':1,'child_count_max':5},
            {'parent_table':'employees','parent_key':'employee_id','child_table':'monthly_performance_summaries','child_key':'employee_id','child_count_min':12,'child_count_max':12},
        ],
    }
    response=json.dumps({'choices':[{'message':{'content':json.dumps(proposal)}}]}).encode()
    monkeypatch.setattr(assistant.urllib.request,'urlopen',lambda *a,**kw:BytesIO(response))
    result=assistant.propose(
        'Create approximately 500 synthetic employees and monthly employee performance '
        'summaries calculated from the generated activity records.'
    )
    spec=result['spec']
    assert next(t for t in spec['tables'] if t['name']=='employees')['rows']==500
    assert all(t['name']!='monthly_performance_summaries' for t in spec['tables'])
    assert result['review']['explicit_row_requirements'][0]['assistant_rows']==100
    assert result['review']['omitted_tables']==['monthly_performance_summaries']
    assert result['review']['unsupported_requests']


def test_completed_job_is_http_serializable(tmp_path,monkeypatch):
    from synthetic_platform import api
    from fastapi.testclient import TestClient
    monkeypatch.setattr(api,'STORAGE',tmp_path)
    s=simple([dict(name='id',type='integer',role='identifier'),dict(name='amount',type='integer',role='rule',rule={'kind':'integer_range','start':0,'end':100})],primary_key='id')
    api.JOBS['httpcheck']={'id':'httpcheck'}
    api._run_job('httpcheck',s,None,None)
    try:
        with TestClient(api.app) as client:
            response=client.get('/api/jobs/httpcheck')
            assert response.status_code==200
            assert response.json()['status']=='completed'
            assert all(type(c['passed']) is bool for c in response.json()['report']['tables'][0]['constraints'])
            assert client.get('/api/jobs/httpcheck/download/records').status_code==200
    finally:api.JOBS.pop('httpcheck',None)


def test_validate_returns_complete_ui_specification():
    from synthetic_platform.api import validate_spec, ValidateRequest
    response=validate_spec(ValidateRequest(spec=dict(name='minimal',mode='schema_rules',purpose='software_testing',tables=[dict(name='records',columns=[dict(name='id',type='integer',role='identifier')])])))
    assert response['ok']
    assert response['spec']['tables'][0]['constraints']==[]
    assert response['spec']['relationships']==[]
    assert response['spec']['privacy']['release_claim_permitted'] is False
