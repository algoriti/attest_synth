"""Platform smoke benchmark: public data, fixed specs, no data-derived rule discovery.

Run from any directory. Child processes isolate peak RSS and generator random state.
Copy control is registered in the benchmark process only, never in the app registry.
"""
import argparse,json,os,sys,subprocess,time,resource
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'platform/backend'
sys.path.insert(0,str(BACKEND))
OUT=Path(__file__).with_name('results');OUT.mkdir(exist_ok=True)


def trial(dataset,engine,seed):
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from synthetic_platform.spec import SyntheticDataSpec
    from synthetic_platform.pipeline import run
    from synthetic_platform.engines.base import EngineAdapter,GenerationOutcome,register
    from synthetic_platform.engines.learned import IndependentEngine
    @register
    class CopyControl(EngineAdapter):
        name='copy_control'
        def capabilities(self):return {**IndependentEngine().capabilities(),'name':self.name}
        def generate(self,spec,table,rows,source=None):
            frame=source.sample(n=rows,replace=True,random_state=spec.seed).reset_index(drop=True)
            return GenerationOutcome(frame=frame,engine=self.name,requested_rows=rows,generated_rows=len(frame),warnings=['BENCHMARK ONLY: copies source rows; no privacy.'])
    path=ROOT/'literature-review/benchmarks/data'
    file,cols,target,task={
        'bank':('bank.csv',['age','job','marital','education','balance','housing','loan','campaign','previous','poutcome','y'],'y','classification'),
        'student':('student-mat.csv',['school','sex','age','studytime','failures','schoolsup','higher','internet','absences','G1','G2','G3'],'G3','regression'),
        'wine':('winequality-red.csv',None,'quality','regression')}[dataset]
    frame=pd.read_csv(path/file,sep=None,engine='python')
    if cols:frame=frame[cols]
    frame=frame.drop_duplicates().reset_index(drop=True)
    if len(frame)>1200:
        frame,_=train_test_split(frame,train_size=1200,random_state=2026,stratify=frame[target] if task=='classification' else None)
        frame=frame.reset_index(drop=True)
    columns=[dict(name=n,type='category' if frame[n].dtype=='object' else 'integer' if pd.api.types.is_integer_dtype(frame[n]) else 'number',role='learned',nullable=False,provenance={'origin':'user','confirmed':True,'detail':'Fixed benchmark schema; no fitted policy discovery.'}) for n in frame]
    spec=SyntheticDataSpec.model_validate(dict(name=dataset,mode='learned_table',purpose='ml_development',engine=engine,seed=seed,
        tables=[dict(name=dataset,rows=int(len(frame)*.75),columns=columns,source={'kind':'public_records'})],
        evaluation={'checks':['schema','constraints','fidelity','predictive_utility'],'target':target,'task':task}))
    start=time.perf_counter()
    result=run(spec,sources={dataset:frame})
    report=result['report']
    return dict(dataset=dataset,engine=engine,seed=seed,seconds=time.perf_counter()-start,
        peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        summary=report['summary'],evaluation=report['evaluation'],environment=report['environment'],
        repairs=report['tables'][0]['repairs'],artifact_sha256=report['reproduction']['artifact_sha256'],
        qualification='Exploratory platform benchmark with one downstream random forest, not a privacy audit or universal engine ranking.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset');parser.add_argument('--engine');parser.add_argument('--seed',type=int);args=parser.parse_args()
    if args.dataset:
        try: result=trial(args.dataset,args.engine,args.seed)
        except Exception as e: result=dict(dataset=args.dataset,engine=args.engine,seed=args.seed,error=f'{type(e).__name__}: {e}')
        (OUT/f'{args.dataset}_{args.engine}_{args.seed}.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    else:
        results=[]
        for dataset in ['bank','student','wine']:
            for engine in ['independent','arf','copy_control']:
                for seed in [11,29,47]:
                    proc=subprocess.run([sys.executable,__file__,'--dataset',dataset,'--engine',engine,'--seed',str(seed)],capture_output=True,text=True,timeout=120)
                    path=OUT/f'{dataset}_{engine}_{seed}.json'
                    result=json.loads(path.read_text()) if path.exists() else dict(dataset=dataset,engine=engine,seed=seed,error=proc.stderr[-500:])
                    results.append(result);print(dataset,engine,seed,'ERROR '+result['error'] if 'error' in result else 'ok',flush=True)
        (OUT/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
