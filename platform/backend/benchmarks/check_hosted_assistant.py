"""One schema-only provider check. Reads credentials server-side; never prints them."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from synthetic_platform.assistant import propose,configuration
from synthetic_platform.pipeline import run
from synthetic_platform.spec import SyntheticDataSpec
out=Path(__file__).with_name('results')/'hosted_assistant_check.json'
started=time.perf_counter()
try:
    answer=propose('Create a small software-testing dataset: one table named products with 10 rows, an integer product_id identifier, and a numeric unit_price sampled uniformly from 1 to 50. Use the rules engine. No real records or names.')
    result=run(SyntheticDataSpec.model_validate(answer['spec']))
    report={'model':configuration()['model'],'provider':'Groq','status':'completed','seconds':time.perf_counter()-started,'spec':answer['spec'],'summary':result['report']['summary'],'data_sent':'User scenario and specification JSON schema only; no uploaded records.'}
except Exception as exc:
    report={'model':configuration()['model'],'provider':'Groq','status':'failed','seconds':time.perf_counter()-started,'error':str(exc)}
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='spec'},indent=2))
if report['status']=='failed':sys.exit(1)
