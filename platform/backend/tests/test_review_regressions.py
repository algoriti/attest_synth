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
from synthetic_platform.derive import DerivationError, apply_derived, evaluate
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
    assert len(requests[1]['messages'])==3
    assert all(message['role']!='assistant' for message in requests[1]['messages'])


def test_hosted_assistant_reports_failure_after_one_bad_json_repair(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    monkeypatch.setattr(assistant.urllib.request,'urlopen',lambda *a,**kw:BytesIO(b'{"choices":[{"message":{"content":"not JSON"}}]}'))
    with pytest.raises(ValueError,match="first proposal was not executable.*JSONDecodeError.*after one correction attempt"):
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
                {'name':'attendance_rate','type':'number','role':'derived','formula':{'op':'/','args':[{'const':1},{'const':2}]}}]},
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


def test_hosted_assistant_reconciles_relationship_owned_keys_without_second_call(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    proposal={
        'name':'orders','mode':'relational_rules','purpose':'software_testing','engine':'relational_rules',
        'tables':[
            {'name':'customers','rows':100,'primary_key':'customer_id','columns':[
                {'name':'customer_id','type':'integer','role':'identifier'}]},
            {'name':'orders','rows':100,'primary_key':'order_id','columns':[
                {'name':'order_id','type':'integer','role':'identifier'},
                {'name':'customer_id','type':'integer','role':'rule','rule':{'kind':'integer_range','start':1,'end':100}}]},
        ],
        'relationships':[{'parent_table':'customers','parent_key':'customer_id','child_table':'orders','child_key':'customer_id','child_count_min':1,'child_count_max':5}],
    }
    response=json.dumps({'choices':[{'message':{'content':json.dumps(proposal)},'finish_reason':'stop'}]}).encode()
    calls=[]
    def fake_open(*args,**kwargs):
        calls.append(1);return BytesIO(response)
    monkeypatch.setattr(assistant.urllib.request,'urlopen',fake_open)
    result=assistant.propose('Create approximately 500 synthetic customers with linked orders.')
    customers,orders=result['spec']['tables']
    assert customers['rows']==500
    assert orders['rows'] is None
    foreign_key=next(column for column in orders['columns'] if column['name']=='customer_id')
    assert foreign_key['role']=='foreign_key' and foreign_key['rule'] is None
    assert len(calls)==1
    assert result['review']['automatic_reconciliations']


def test_upload_revision_sends_schema_only_and_returns_reviewable_column(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    spec=SyntheticDataSpec.model_validate({
        'name':'private_students','mode':'learned_table','purpose':'analytics','engine':'independent',
        'tables':[{'name':'students','rows':20,'source':{'kind':'uploaded_csv','row_count':20,'sha256':'secret-hash'},'columns':[
            {'name':'age','type':'integer','role':'learned','nullable':False},
            {'name':'private_note','type':'string','role':'learned','nullable':True},
        ]}],
    })
    plan={'changes':[{'action':'add_column','table':'students','column':{
        'name':'age_band','type':'category','role':'derived','formula':{'op':'if_else','args':[{'op':'lt','args':[{'col':'age'},{'const':21}]},{'const':'under_21'},{'const':'21_plus'}]}
    }}],'assumptions':['The age bands are user-reviewable demonstration categories.']}
    seen={}
    def fake_open(request,timeout):
        seen.update(json.loads(request.data));return BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(plan)}}]}).encode())
    monkeypatch.setattr(assistant.urllib.request,'urlopen',fake_open)
    result=assistant.revise_uploaded_spec('Add an age band based on the existing age column.',spec)
    sent=json.dumps(seen)
    assert 'secret-hash' not in sent and 'row_count' not in sent and 'upload_id' not in sent
    assert 'age' in sent and 'private_note' in sent
    table=result['spec']['tables'][0]
    assert table['source']['kind']=='uploaded_csv'
    added=next(column for column in table['columns'] if column['name']=='age_band')
    assert added['role']=='derived' and added['provenance']['origin']=='assistant_proposed'
    assert 'record values' in result['disclosure']['excluded']


def test_upload_revision_omits_independent_performance_field_when_relation_requested(monkeypatch):
    from synthetic_platform import assistant
    from io import BytesIO
    monkeypatch.setenv('SYNTHETIC_LLM_API_KEY','test-only')
    spec=SyntheticDataSpec.model_validate({
        'name':'attendance','mode':'learned_table','purpose':'analytics','engine':'independent',
        'tables':[{'name':'attendance','rows':20,'source':{'kind':'uploaded_csv'},'columns':[
            {'name':'late_status','type':'boolean','role':'learned'},
        ]}],
    })
    plan={'changes':[{'action':'add_column','table':'attendance','column':{
        'name':'quality_score','type':'number','role':'rule','rule':{'kind':'number_range','start':0,'end':100}
    }}],'assumptions':[]}
    monkeypatch.setattr(assistant.urllib.request,'urlopen',lambda request,timeout:BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(plan)}}]}).encode()))
    result=assistant.revise_uploaded_spec('Add a quality score highly related to attendance.',spec)
    assert not any(c['name']=='quality_score' for c in result['spec']['tables'][0]['columns'])
    assert any('Omitted independently sampled' in a for a in result['assumptions'])


def test_learned_pipeline_merges_locally_generated_rule_columns():
    source=pd.DataFrame({'age':np.tile(np.arange(17,27),12)})
    spec=SyntheticDataSpec.model_validate({
        'name':'hybrid','mode':'learned_table','purpose':'software_testing','engine':'independent',
        'tables':[{'name':'students','rows':30,'source':{'kind':'uploaded_csv'},'columns':[
            {'name':'age','type':'integer','role':'learned'},
            {'name':'review_status','type':'category','role':'rule','rule':{'kind':'choice','values':['pending','reviewed']}},
        ]}],
    })
    result=run(spec,sources={'students':source})
    assert set(result['frames']['students'].review_status)<= {'pending','reviewed'}
    assert len(result['frames']['students'])==30
    assert any('generated locally' in warning for warning in result['report']['tables'][0]['warnings'])


def test_validator_rejects_formula_output_type_mismatch():
    s=simple([
        dict(name='event_time',type='timestamp',role='rule',rule={'kind':'timestamp_range','start':'2026-01-01','end':'2026-01-02'}),
        dict(name='time_label',type='string',role='derived',formula={'op':'time_of_day','args':[{'col':'event_time'}]}),
    ])
    result=validate(s,get_engine('rules').capabilities())
    assert any(f.code=='formula_result_type' for f in result.errors)


def test_validator_rejects_required_formula_over_nullable_input():
    s=simple([
        dict(name='hours',type='number',role='rule',nullable=True,null_fraction=.1,rule={'kind':'number_range','start':0,'end':10}),
        dict(name='overtime',type='boolean',role='derived',formula={'op':'gt','args':[{'col':'hours'},{'const':8}]}),
    ])
    result=validate(s,get_engine('rules').capabilities())
    assert any(f.code=='formula_nullable_input' for f in result.errors)


def test_min_max_expressions_mix_series_and_scalar():
    frame=pd.DataFrame({'hours':[-2,3,12]})
    low=evaluate(Expr.model_validate({'op':'max','args':[{'col':'hours'},{'const':0}]}),frame)
    capped=evaluate(Expr.model_validate({'op':'min','args':[{'col':'hours'},{'const':8}]}),frame)
    assert list(low)==[0,3,12]
    assert list(capped)==[-2,3,8]


def test_duration_argument_order_reconciles_clear_clock_out_clock_in_reversal():
    from synthetic_platform.assistant import _normalize_duration_argument_order
    formula={'op':'duration_hours','args':[{'col':'attendance_time_out'},{'col':'attendance_time_in'}]}
    assert _normalize_duration_argument_order(formula)==1
    assert [arg['col'] for arg in formula['args']]==['attendance_time_in','attendance_time_out']


def test_validator_rejects_generic_subtraction_of_timestamps():
    s=simple([
        dict(name='start',type='timestamp',role='rule',rule={'kind':'timestamp_range','start':'2026-01-01','end':'2026-01-02'}),
        dict(name='end',type='timestamp',role='rule',rule={'kind':'timestamp_range','start':'2026-01-02','end':'2026-01-03'}),
        dict(name='hours',type='number',role='derived',formula={'op':'sub','args':[{'col':'end'},{'col':'start'}]}),
    ])
    result=validate(s,get_engine('rules').capabilities())
    assert any(f.code=='formula_result_type' for f in result.errors)


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
