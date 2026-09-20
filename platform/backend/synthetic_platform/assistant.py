"""Optional hosted specification assistant. This module never reads uploaded records."""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from .spec import SyntheticDataSpec, Origin, Provenance
from .validator import validate
from .engines.base import get_engine, choose_engine


def _settings():
    # Read only named settings; never evaluate shell syntax or expose credentials.
    local = {}
    path = Path(__file__).resolve().parents[1] / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip() in {'GROQ_API_KEY','SYNTHETIC_LLM_API_KEY','SYNTHETIC_LLM_BASE_URL','SYNTHETIC_LLM_MODEL','SYNTHETIC_LLM_REASONING'}:
                local[key.strip()] = value.strip().strip('"').strip("'")
    def setting(key, default=''):
        return os.environ.get(key) or local.get(key) or default
    return {'key':setting('SYNTHETIC_LLM_API_KEY',setting('GROQ_API_KEY')),
            'base':setting('SYNTHETIC_LLM_BASE_URL','https://api.groq.com/openai/v1'),
            'model':setting('SYNTHETIC_LLM_MODEL','openai/gpt-oss-120b'),
            'reasoning':setting('SYNTHETIC_LLM_REASONING','high')}


def configuration():
    settings=_settings()
    return {'configured':bool(settings['key']), 'model':settings['model'],
            'data_policy':'Only your instructions and the platform specification format are sent. Uploaded records are never included.'}



def propose(prompt):
    if not configuration()['configured']:
        raise ValueError('The administrator must configure the hosted model URL, model name and API key first.')
    settings=_settings()
    base=settings['base'].rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('Hosted model connections require an HTTPS base URL.')
    instruction=(
        'Propose a synthetic data specification as JSON, not generated data. Use only schema_rules/rules '
        'or relational_rules/relational_rules modes/engines. No source records are available. '
        'Mark assumptions assistant_proposed and confirmed false. Start small (100 rows per root). '
        'Declare identifier primary keys, matching foreign-key types, and explicit count bounds. '
        'Use compound unique_keys for a junction when each parent pair should appear once. '
        'Use no formal privacy claims. Do not invent a user confirmation. '
        'Return exactly one object matching this schema: '+json.dumps(SyntheticDataSpec.model_json_schema())
    )
    payload={'model':settings['model'], 'messages':[{'role':'system','content':instruction},{'role':'user','content':prompt}],
             'response_format':{'type':'json_object'},'reasoning_effort':settings['reasoning'],'max_completion_tokens':16000}
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+settings['key'],'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Model response exceeded the supported size.')
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Model provider returned HTTP {exc.code}. Check the configured model and credentials.') from None
    except (urllib.error.URLError,TimeoutError):
        raise ValueError('Could not reach the model provider within the request timeout. Retry or use the guided editor.') from None
    try:
        content=json.loads(raw)['choices'][0]['message']['content']
        spec=SyntheticDataSpec.model_validate_json(content)
    except (ValueError,KeyError,IndexError,TypeError):
        raise ValueError('The model did not return a valid platform specification. Refine the request or use the guided editor.') from None
    if spec.mode.value not in ('schema_rules','relational_rules'):
        raise ValueError('The assistant may propose only scenarios without source records.')
    for table in spec.tables:
        if table.source.kind.value!='none':raise ValueError('The assistant cannot attach source records.')
        for item in [*table.columns,*table.constraints]:
            item.provenance=Provenance(origin=Origin.ASSISTANT_PROPOSED,detail='Hosted assistant proposal; review before relying on it.')
    for rel in spec.relationships:
        rel.provenance=Provenance(origin=Origin.ASSISTANT_PROPOSED,detail='Proposed relationship; review cardinalities.')
    try: caps=get_engine(choose_engine(spec)).capabilities()
    except KeyError:raise ValueError('The assistant selected an unavailable engine.') from None
    result=validate(spec,caps)
    if not result.ok:raise ValueError('Proposed specification needs correction: '+'; '.join(f.message for f in result.errors))
    return {'spec':spec.model_dump(mode='json'),'validation':result.as_dict(),'model':configuration()['model'],
            'notice':'Proposal only. Review its rules and assumptions before generating.'}
