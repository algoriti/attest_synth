"""Optional hosted specification assistant. This module never reads uploaded records."""
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from .spec import SemanticRole, SyntheticDataSpec, Origin, Provenance
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



def _json_object(content: str) -> str:
    """Tolerate a fenced response while still validating one JSON object strictly."""
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    start, end = candidate.find("{"), candidate.rfind("}")
    return candidate[start:end + 1] if start >= 0 and end > start else candidate


def _schema_error_summary(exc: Exception) -> str:
    """Describe structural failures without echoing the model's proposed values."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        items = []
        for error in errors()[:8]:
            location = ".".join(str(part) for part in error.get("loc", ())) or "specification"
            items.append(f"{location}: {error.get('msg', 'invalid value')}")
        if items:
            return "; ".join(items)
    message = str(exc).splitlines()[0].strip()
    return f"{type(exc).__name__}: {message[:500]}"


def _period_summary_requested(prompt: str) -> bool:
    text = prompt.lower()
    return (
        bool(re.search(r"\b(monthly|month|period)\b", text))
        and bool(re.search(r"\b(summary|summaries|indicator|indicators)\b", text))
        and bool(
            re.search(
                r"\b(calculat\w*|comput\w*|deriv\w*|from (?:the )?generated|activity records)",
                text,
            )
        )
    )


def _remove_unsupported_period_summaries(
    prompt: str, spec: SyntheticDataSpec
) -> tuple[list[str], list[str]]:
    """Never replace requested employee-period calculations with random numbers."""
    if not _period_summary_requested(prompt):
        return [], []
    summary_name = re.compile(r"(summary|summaries|monthly.*behavior|performance.*period)")
    removed = [table.name for table in spec.tables if summary_name.search(table.name.lower())]
    if removed:
        keep = {table.name for table in spec.tables if table.name not in removed}
        spec.tables = [table for table in spec.tables if table.name in keep]
        spec.relationships = [
            relationship for relationship in spec.relationships
            if relationship.parent_table in keep and relationship.child_table in keep
        ]
        spec.aggregates = [
            aggregate for aggregate in spec.aggregates
            if aggregate.parent_table in keep and aggregate.child_table in keep
        ]
        spec.cross_table_constraints = [
            constraint for constraint in spec.cross_table_constraints
            if constraint.parent_table in keep and constraint.child_table in keep
        ]
    limitation = (
        "Monthly or other entity-period summaries calculated across several activity tables "
        "are not supported by the current engine. They were omitted instead of being filled "
        "with unrelated random values. Generate the base event tables first; period summaries "
        "remain a separate, explicit implementation step."
    )
    return removed, [limitation]


def _enforce_explicit_row_requirements(prompt: str, spec: SyntheticDataSpec) -> list[dict]:
    """Copy explicit '<number> <table>' requirements instead of trusting LLM defaults."""
    text = prompt.lower().replace("_", " ")
    enforced: list[dict] = []
    for table in spec.tables:
        label = table.name.lower().replace("_", " ")
        aliases = {label}
        if label.endswith("ies"):
            aliases.add(label[:-3] + "y")
        elif label.endswith("s"):
            aliases.add(label[:-1])
        match = None
        for alias in sorted(aliases, key=len, reverse=True):
            pattern = re.compile(
                rf"\b(?P<qualifier>approximately|about|around|roughly)?\s*"
                rf"(?P<count>[1-9][\d,]*)\s+(?:synthetic\s+)?{re.escape(alias)}\b"
            )
            match = pattern.search(text)
            if match and text[max(0, match.start() - 3):match.start()] != "to ":
                break
            match = None
        if match is None:
            continue
        count = int(match.group("count").replace(",", ""))
        previous = table.rows
        table.rows = count
        enforced.append(
            {
                "table": table.name,
                "requested_rows": count,
                "qualifier": match.group("qualifier") or "exact",
                "assistant_rows": previous,
                "changed": previous != count,
            }
        )
    return enforced


def _assistant_semantic_errors(spec: SyntheticDataSpec) -> list[str]:
    errors: list[str] = []
    for relationship in spec.relationships:
        child = spec.table(relationship.child_table)
        foreign_key = child.column(relationship.child_key) if child else None
        if foreign_key is not None and foreign_key.role != SemanticRole.FOREIGN_KEY:
            errors.append(
                f"{relationship.child_table}.{relationship.child_key} is assigned by a "
                "relationship and must use role 'foreign_key' with no sampling rule"
            )
    return errors


def propose(prompt, _repair=None):
    if not configuration()['configured']:
        raise ValueError('The administrator must configure the hosted model URL, model name and API key first.')
    settings=_settings()
    base=settings['base'].rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('Hosted model connections require an HTTPS base URL.')
    instruction=(
        'Propose a synthetic data specification as JSON, not generated data. Use only schema_rules/rules '
        'or relational_rules/relational_rules modes/engines. No source records are available. '
        'Preserve every explicit user quantity, duration, named entity, requested field, and constraint. '
        'Use 100 rows only for a root table whose size the user did not state. For relationship-owned '
        'child tables, leave rows null unless the user gave an explicit total; declare feasible count bounds. '
        'Mark assumptions assistant_proposed and confirmed false. '
        'Declare identifier primary keys and matching foreign keys with role foreign_key and no rule; '
        'their values are assigned only by relationships. '
        'Use compound unique_keys for a junction when each parent pair should appear once. '
        'Use no formal privacy claims. Do not invent a user confirmation. '
        'Every independently generated non-ID/non-FK column MUST have role rule and a rule object. Example: '
        '{"name":"price","type":"number","role":"rule","rule":{"kind":"number_range","start":1,"end":50}}. '
        'Use derived only for a same-table formula. Use aggregate only for a supported direct-child '
        'count/sum/mean/min/max grouped by one parent key. The platform cannot compute employee-by-month '
        'or other entity-period summaries across several activity tables: omit such summary tables rather '
        'than inventing their measures as random rules. Same-table date ordering belongs in table constraints. '
        'Do not add entities the user did not request. Keep the JSON compact by omitting fields that use defaults. '
        'Return exactly one object matching this schema: '+json.dumps(SyntheticDataSpec.model_json_schema())
    )
    payload={'model':settings['model'], 'messages':[{'role':'system','content':instruction},{'role':'user','content':prompt}],
             'response_format':{'type':'json_object'},'reasoning_effort':settings['reasoning'],'max_completion_tokens':24000}
    if _repair is not None:
        payload['messages'].extend([{'role':'assistant','content':_repair[0]},
            {'role':'user','content':'The platform rejected that proposal. Correct these errors and return the complete JSON specification: '+_repair[1]}])
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+settings['key'],'Content-Type':'application/json','Accept':'application/json','User-Agent':'SyntheticDataPlatform/0.1'})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Model response exceeded the supported size.')
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            body = json.loads(exc.read(4096))
            error = body.get('error', {})
            detail = str(error.get('message', ''))[:300] if isinstance(error,dict) else str(error)[:300]
        except (ValueError, AttributeError):
            detail = 'Provider gateway rejected the request.'
        detail = detail.replace(settings['key'], '[redacted]')
        raise ValueError(f'Model provider returned HTTP {exc.code}. {detail}') from None
    except (urllib.error.URLError,TimeoutError):
        raise ValueError('Could not reach the model provider within the request timeout. Retry or use the guided editor.') from None
    finish_reason = "unknown"
    try:
        completion=json.loads(raw)
        choice=completion['choices'][0]
        finish_reason=str(choice.get('finish_reason','unknown'))
        content=choice['message']['content']
        spec=SyntheticDataSpec.model_validate_json(_json_object(content))
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        structural_error = _schema_error_summary(exc)
        if _repair is None:
            prior = content[:12000] if isinstance(locals().get('content'), str) else '{}'
            return propose(
                prompt,
                (prior, f"Invalid JSON or schema (provider finish reason: {finish_reason}): {structural_error}"),
            )
        raise ValueError(
            'The hosted model could not produce an executable specification after one correction attempt. '
            f'Last structural error (provider finish reason: {finish_reason}): {structural_error}. '
            'Try requesting the base entities first, then add relationships in the guided editor. '
            'Entity-period summaries across several activity tables are not supported yet.'
        ) from None
    if spec.mode.value not in ('schema_rules','relational_rules'):
        raise ValueError('The assistant may propose only scenarios without source records.')
    removed_tables, limitations = _remove_unsupported_period_summaries(prompt, spec)
    explicit_rows = _enforce_explicit_row_requirements(prompt, spec)
    for table in spec.tables:
        if table.source.kind.value!='none':raise ValueError('The assistant cannot attach source records.')
        for column in table.columns:
            detail = (
                f"The assistant proposed how to create '{table.name}.{column.name}'. "
                "Review its values, bounds and meaning; no organizational policy or distribution was supplied."
            )
            if column.role == SemanticRole.FOREIGN_KEY:
                detail = f"The assistant proposed '{table.name}.{column.name}' as a relationship-owned foreign key."
            column.provenance=Provenance(origin=Origin.ASSISTANT_PROPOSED,detail=detail)
        for constraint in table.constraints:
            constraint.provenance=Provenance(
                origin=Origin.ASSISTANT_PROPOSED,
                detail=f"The assistant proposed this constraint for '{table.name}'; review its policy meaning.",
            )
    for rel in spec.relationships:
        rel.provenance=Provenance(
            origin=Origin.ASSISTANT_PROPOSED,
            detail=(f"The assistant proposed {rel.parent_table}->{rel.child_table}; review "
                    f"the {rel.child_count_min}..{rel.child_count_max} children-per-parent bounds."),
        )
    try: caps=get_engine(choose_engine(spec)).capabilities()
    except KeyError:raise ValueError('The assistant selected an unavailable engine.') from None
    result=validate(spec,caps)
    semantic_errors = _assistant_semantic_errors(spec)
    if not result.ok or semantic_errors:
        errors='; '.join([*(f.message for f in result.errors), *semantic_errors])
        if _repair is None:
            return propose(prompt, (spec.model_dump_json(), errors))
        raise ValueError('Proposed specification needs correction: '+errors)
    return {'spec':spec.model_dump(mode='json'),'validation':result.as_dict(),'model':configuration()['model'],
            'notice':'Proposal only. Review its rules and assumptions before generating.',
            'review':{
                'correction_attempted':_repair is not None,
                'explicit_row_requirements':explicit_rows,
                'unsupported_requests':limitations,
                'omitted_tables':removed_tables,
            }}
