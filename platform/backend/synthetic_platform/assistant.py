"""Optional hosted specification assistant. This module never reads uploaded records."""
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from .spec import (
    Column,
    ColumnType,
    ConstraintOperator,
    Expr,
    SemanticRole,
    SyntheticDataSpec,
    Origin,
    Provenance,
)
from .validator import validate, _expression_may_be_null
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


def schema_manifest(spec: SyntheticDataSpec) -> dict:
    """The complete and deliberately small disclosure used for upload revisions."""
    return {
        "dataset": spec.name,
        "mode": spec.mode.value,
        "tables": [
            {
                "name": table.name,
                "primary_key": table.primary_key,
                "columns": [
                    {
                        "name": column.name,
                        "type": column.type.value,
                        "role": column.role.value,
                        "nullable": column.nullable,
                    }
                    for column in table.columns
                ],
            }
            for table in spec.tables
        ],
    }


def revise_uploaded_spec(prompt: str, spec: SyntheticDataSpec, _repair: str | None = None) -> dict:
    """Propose schema changes without sending records, values, statistics or hashes."""
    if not configuration()["configured"]:
        raise ValueError("The administrator must configure the hosted model first.")
    settings = _settings()
    manifest = schema_manifest(spec)
    contract = (
        'Return one compact JSON object: {"changes":[Change],"assumptions":[string]}. '
        'Change is one of: '
        '{"action":"add_column","table":string,"column":Column}, '
        '{"action":"update_column","table":string,"column_name":string,"column":Column}, or '
        '{"action":"add_constraint","table":string,"constraint":Constraint}. '
        'Column uses the same compact Column contract below. New columns cannot be learned, identifiers, '
        'foreign keys or aggregates; use rule, derived, constant or empty. Do not rename columns. '
        'Use only existing column names inside formulas. Return no generated records or example values '
        'taken from data. '+_compact_contract().split('Column: ',1)[1]
    )
    instruction = (
        'You revise a synthetic-data specification created from an uploaded dataset. You receive only a '
        'schema manifest: table and column names, types, roles and nullability. You never receive records, '
        'previews, statistics, hashes, category values or identifiers. Follow the requested transformation '
        'without claiming it was learned from the data. Every proposed change is an unconfirmed assumption. '
        'Rule columns are sampled independently by this platform. Never claim that independently sampled rule '
        'columns are correlated with uploaded columns or with one another. If the user requests a relationship '
        'that the available schema and formula vocabulary cannot represent honestly, omit those columns and '
        'state the limitation in assumptions instead of inventing an unrelated score. Never use {"const":null} '
        'in a formula; represent missingness tests with is_null or not_null. '
        + contract
    )
    user = "Requested change:\n" + prompt + "\n\nApproved schema manifest:\n" + json.dumps(manifest)
    if _repair:
        user += "\n\nThe prior plan was rejected. Regenerate it and correct: " + _repair
    payload = {
        "model": settings["model"],
        "messages": [{"role":"system","content":instruction},{"role":"user","content":user}],
        "response_format":{"type":"json_object"},
        "reasoning_effort":settings["reasoning"],
        "max_completion_tokens":12000,
    }
    base=settings['base'].rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('Hosted model connections require an HTTPS base URL.')
    request=urllib.request.Request(base+'/chat/completions',data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+settings['key'],'Content-Type':'application/json','Accept':'application/json','User-Agent':'SyntheticDataPlatform/0.1'})
    try:
        with urllib.request.urlopen(request,timeout=120) as response:
            raw=response.read(512*1024+1)
            if len(raw)>512*1024:raise ValueError('Model response exceeded the supported size.')
    except urllib.error.HTTPError as exc:
        detail=''
        try:
            body=json.loads(exc.read(4096));error=body.get('error',{})
            detail=str(error.get('message',''))[:300] if isinstance(error,dict) else str(error)[:300]
        except (ValueError,AttributeError):detail='Provider gateway rejected the request.'
        raise ValueError(f'Model provider returned HTTP {exc.code}. {detail.replace(settings["key"],"[redacted]")}') from None
    except (urllib.error.URLError,TimeoutError):
        raise ValueError('Could not reach the model provider within the request timeout.') from None
    try:
        plan=json.loads(_json_object(json.loads(raw)['choices'][0]['message']['content']))
        if not isinstance(plan.get('changes'),list):raise ValueError("'changes' must be a list")
        revised=spec.model_copy(deep=True);summaries=[]
        relationship_keys={(r.child_table,r.child_key) for r in revised.relationships}
        for item in plan['changes']:
            if not isinstance(item,dict):raise ValueError('every change must be an object')
            table=revised.table(str(item.get('table','')))
            if table is None:raise ValueError(f"unknown table '{item.get('table')}'")
            action=item.get('action')
            if action in {'add_column','update_column'}:
                raw_column=item.get('column')
                if not isinstance(raw_column,dict):raise ValueError(f'{action} needs a column')
                container={'mode':'schema_rules','tables':[{'name':'t','columns':[dict(raw_column)]}]}
                _normalize_expression_operators(container)
                duration_repairs=_normalize_duration_argument_order(container)
                _sanitize_model_vocabulary(container)
                column=Column.model_validate(container['tables'][0]['columns'][0])
                nullable_repair=False
                if column.role == SemanticRole.DERIVED and not column.nullable and _expression_may_be_null(column.formula, table):
                    column.nullable=True
                    nullable_repair=True
                if column.role in {SemanticRole.LEARNED,SemanticRole.IDENTIFIER,SemanticRole.FOREIGN_KEY,SemanticRole.AGGREGATE}:
                    raise ValueError(f"'{column.name}' uses role '{column.role.value}', which is not allowed for an AI-added upload column")
                column.provenance=Provenance(origin=Origin.ASSISTANT_PROPOSED,detail=f"Proposed from the user's instruction using schema metadata only; no uploaded values were sent.")
                if action=='add_column':
                    if table.column(column.name):raise ValueError(f"column '{column.name}' already exists")
                    table.columns.append(column);summaries.append(f"Added {table.name}.{column.name} as {column.role.value}.")
                else:
                    old_name=str(item.get('column_name',''))
                    old=table.column(old_name)
                    if old is None:raise ValueError(f"unknown column '{old_name}'")
                    if old_name==table.primary_key or (table.name,old_name) in relationship_keys:raise ValueError(f"key column '{old_name}' cannot be changed")
                    if column.name!=old_name:raise ValueError('column renaming is not supported in this workflow')
                    table.columns[table.columns.index(old)]=column;summaries.append(f"Updated {table.name}.{old_name} to {column.role.value}.")
                if duration_repairs:
                    summaries.append(f"Corrected start/end argument order in {table.name}.{column.name}.")
                if nullable_repair:
                    summaries.append(f"Marked {table.name}.{column.name} nullable because its formula can receive missing inputs.")
            elif action=='add_constraint':
                from .spec import Constraint
                constraint=Constraint.model_validate(item.get('constraint'))
                constraint.provenance=Provenance(origin=Origin.ASSISTANT_PROPOSED,detail="Proposed from schema metadata only.")
                table.constraints.append(constraint);summaries.append(f"Added {constraint.operator.value} constraint to {table.name}.")
            else:raise ValueError(f"unsupported change action '{action}'")
        if re.search(r"\b(correlat\w*|highly related|relationship|depend\w*|associat\w*)\b", prompt, re.I):
            original={(table.name,column.name) for table in spec.tables for column in table.columns}
            added_rules=[
                f"{table.name}.{column.name}" for table in revised.tables for column in table.columns
                if (table.name,column.name) not in original and column.role == SemanticRole.RULE
            ]
            # Every newly added rule column is independently sampled. None can satisfy
            # an explicit relationship request, whatever the column happens to be named.
            unsupported=added_rules
            if unsupported:
                unsupported_pairs={tuple(name.split('.',1)) for name in unsupported}
                for table in revised.tables:
                    table.columns=[
                        column for column in table.columns
                        if (table.name,column.name) not in unsupported_pairs
                    ]
                summaries=[
                    summary for summary in summaries
                    if not any(name in summary for name in unsupported)
                ]
                removed_names={name.split('.',1)[1] for name in unsupported}
                plan['assumptions']=[
                    assumption for assumption in plan.get('assumptions',[])
                    if not any(name in str(assumption) for name in removed_names)
                    and "performance" not in str(assumption).lower()
                ]
                plan.setdefault('assumptions',[]).append(
                    "Omitted independently sampled performance or quality fields because they cannot satisfy "
                    "the requested relationship. Linked outcome data or a supported conditional model is required."
                )
        caps=get_engine(choose_engine(revised)).capabilities();validation=validate(revised,caps)
        if not validation.ok:raise ValueError('; '.join(f.message for f in validation.errors))
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        if _repair is None:return revise_uploaded_spec(prompt,spec,_schema_error_summary(exc))
        raise ValueError('The assistant could not produce a valid transformation plan after one correction: '+_schema_error_summary(exc)) from None
    return {
        'spec':revised.model_dump(mode='json'),'changes':summaries,
        'assumptions':[str(value)[:500] for value in plan.get('assumptions',[]) if isinstance(value,str)],
        'validation':validation.as_dict(),'model':configuration()['model'],
        'disclosure':{'manifest':manifest,'excluded':['record values','previews','summary statistics','category values','row counts','file name','file hash','upload identifier']},
    }



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


def _is_period_summary_name(name: str) -> bool:
    normalized = name.lower().replace("_", " ")
    return bool(re.search(r"\b(summary|summaries)\b", normalized)) or (
        bool(re.search(r"\b(monthly|period)\b", normalized))
        and bool(re.search(r"\b(performance|behavior|behaviour|indicator|metric)s?\b", normalized))
    )


def _normalize_expression_operators(value) -> None:
    """Translate common mathematical spellings into the platform vocabulary."""
    aliases = {
        "/": "div", "divide": "div", "division": "div",
        "*": "mul", "multiply": "mul", "times": "mul",
        "+": "add", "plus": "add",
        "-": "sub", "subtract": "sub", "minus": "sub",
        ">": "gt", ">=": "ge", "<": "lt", "<=": "le", "==": "eq", "!=": "ne",
    }
    if isinstance(value, dict):
        if isinstance(value.get("op"), str):
            value["op"] = aliases.get(value["op"].lower(), value["op"])
        for child in value.values():
            _normalize_expression_operators(child)
    elif isinstance(value, list):
        for child in value:
            _normalize_expression_operators(child)


def _normalize_duration_argument_order(value) -> int:
    """Repair an unambiguous end/start reversal in duration expressions."""
    repairs=0
    if isinstance(value,dict):
        args=value.get('args')
        if value.get('op') in {'duration_hours','duration_seconds'} and isinstance(args,list) and len(args)==2:
            first=args[0].get('col','') if isinstance(args[0],dict) else ''
            second=args[1].get('col','') if isinstance(args[1],dict) else ''
            start=re.compile(r"(^|_)(time_?in|start|started|assigned|required)(_|$)",re.I)
            end=re.compile(r"(^|_)(time_?out|end|ended|completion|completed|submission|submitted)(_|$)",re.I)
            if end.search(first) and start.search(second):
                value['args']=[args[1],args[0]]
                repairs+=1
        for child in value.values():
            repairs+=_normalize_duration_argument_order(child)
    elif isinstance(value,list):
        for child in value:
            repairs+=_normalize_duration_argument_order(child)
    return repairs


def _default_rule(column_type: str) -> dict:
    if column_type == "boolean":
        return {"kind": "choice", "values": [True, False]}
    if column_type == "category":
        return {"kind": "choice", "values": ["A", "B"]}
    if column_type == "string":
        return {"kind": "faker", "provider": "word"}
    if column_type == "uuid":
        return {"kind": "uuid4"}
    if column_type in {"date", "timestamp"}:
        return {
            "kind": "date_range" if column_type == "date" else "timestamp_range",
            "start": "2025-01-01",
            "end": "2025-12-31",
        }
    return {
        "kind": "integer_range" if column_type == "integer" else "number_range",
        "start": 0,
        "end": 100,
    }


def _sanitize_model_vocabulary(proposal: dict) -> None:
    """Normalize mechanical model vocabulary; no domain assumptions are introduced."""
    mode_aliases = {"rules": "schema_rules", "relational": "relational_rules"}
    purpose_aliases = {
        "ai_ml": "ml_development", "machine_learning": "ml_development",
        "testing": "software_testing", "simulation": "scenario_simulation",
    }
    type_aliases = {
        "int": "integer", "float": "number", "decimal": "number",
        "datetime": "timestamp", "text": "string", "categorical": "category",
    }
    role_aliases = {
        "generated": "rule", "computed": "derived", "formula": "derived",
        "foreign key": "foreign_key", "foreign-key": "foreign_key", "id": "identifier",
    }
    proposal["mode"] = mode_aliases.get(proposal.get("mode"), proposal.get("mode", "schema_rules"))
    # A proposal that links tables is relational by definition. The model sometimes
    # kept "schema_rules" while declaring relationships, which the validator then
    # rejected; the mode follows mechanically from the proposal's own structure.
    if proposal.get("relationships"):
        proposal["mode"] = "relational_rules"
    proposal["purpose"] = purpose_aliases.get(
        proposal.get("purpose"), proposal.get("purpose", "software_testing")
    )
    proposal["engine"] = (
        "relational_rules" if proposal.get("mode") == "relational_rules" else "rules"
    )
    proposal["privacy"] = {
        **(proposal.get("privacy") if isinstance(proposal.get("privacy"), dict) else {}),
        "mechanism": "none",
        "release_claim_permitted": False,
    }
    if not isinstance(proposal.get("evaluation"), dict):
        proposal["evaluation"] = {"checks": ["schema", "constraints"]}
    for table in proposal.get("tables", []):
        if not isinstance(table, dict):
            continue
        table["source"] = {"kind": "none"}
        if isinstance(table.get("rows"), str):
            digits = table["rows"].replace(",", "").strip()
            table["rows"] = int(digits) if digits.isdigit() else None
        primary_key = table.get("primary_key")
        for column in table.get("columns", []):
            if not isinstance(column, dict):
                continue
            column.pop("provenance", None)
            column_type = type_aliases.get(column.get("type"), column.get("type", "string"))
            column["type"] = column_type
            role = role_aliases.get(column.get("role"), column.get("role"))
            if column.get("name") == primary_key:
                role = "identifier"
            elif role is None:
                role = "derived" if column.get("formula") else "rule"
            if role == "derived" and not isinstance(column.get("formula"), dict):
                role = "rule"
            column["role"] = role
            if role == "rule" and not isinstance(column.get("rule"), dict):
                column["rule"] = _default_rule(column_type)
            if role == "foreign_key":
                column.pop("rule", None)
                column.pop("formula", None)
        for constraint in table.get("constraints", []):
            if isinstance(constraint, dict):
                constraint.pop("provenance", None)
                names = constraint.get("columns") or []
                if constraint.get("operator") == "implies_null" and len(names) == 2:
                    for column in table.get("columns", []):
                        if isinstance(column, dict) and column.get("name") == names[1]:
                            column["nullable"] = True
    for relationship in proposal.get("relationships", []):
        if isinstance(relationship, dict):
            relationship.pop("provenance", None)


def _prepare_model_output(prompt: str, content: str) -> tuple[dict, list[str]]:
    """Perform syntax-only cleanup before the strict platform model is constructed."""
    proposal = json.loads(_json_object(content))
    if not isinstance(proposal, dict):
        raise ValueError("the response root must be a JSON object")
    removed: list[str] = []
    if _period_summary_requested(prompt) and isinstance(proposal.get("tables"), list):
        removed = [
            table.get("name", "unnamed_summary")
            for table in proposal["tables"]
            if isinstance(table, dict) and _is_period_summary_name(str(table.get("name", "")))
        ]
        if removed:
            keep = {
                table.get("name") for table in proposal["tables"]
                if isinstance(table, dict) and table.get("name") not in removed
            }
            proposal["tables"] = [
                table for table in proposal["tables"]
                if isinstance(table, dict) and table.get("name") in keep
            ]
            for collection in ("relationships", "aggregates", "cross_table_constraints"):
                if isinstance(proposal.get(collection), list):
                    proposal[collection] = [
                        item for item in proposal[collection]
                        if isinstance(item, dict)
                        and item.get("parent_table") in keep
                        and item.get("child_table") in keep
                    ]
    _normalize_expression_operators(proposal)
    _sanitize_model_vocabulary(proposal)
    return proposal, removed


def _compact_contract() -> str:
    return '''Return one compact JSON object with this contract. Omit provenance, source, and fields using defaults.
Top level: {"name":string,"mode":"schema_rules"|"relational_rules","purpose":"software_testing"|"teaching"|"analytics"|"ml_development"|"scenario_simulation","engine":"rules"|"relational_rules","tables":[Table],"relationships":[Relationship],"aggregates":[],"cross_table_constraints":[],"privacy":{"protected_entity":string|null,"mechanism":"none","release_claim_permitted":false},"evaluation":{"checks":["schema","constraints","cardinality"]}}.
Table: {"name":snake_case,"rows":integer|null,"primary_key":string,"unique_keys":[[string]],"columns":[Column],"constraints":[Constraint]}.
Column: {"name":snake_case,"type":"integer"|"number"|"boolean"|"category"|"string"|"date"|"timestamp"|"uuid","role":"identifier"|"foreign_key"|"rule"|"derived","description":string,"nullable":boolean,"rule":Rule,"formula":Expr}. Include rule only for role rule; include formula only for role derived. Foreign keys have no rule.
Rule: {"kind":"faker"|"sequence"|"uuid4"|"choice"|"integer_range"|"number_range"|"date_range"|"timestamp_range"|"normal","provider":string,"prefix":string,"start":value,"end":value,"values":[value],"weights":[number],"mean":number,"stddev":number,"decimals":integer}. Include only fields used by that kind.
Expr is exactly one of {"col":string}, {"const":value}, or {"op":"add"|"sub"|"mul"|"div"|"round"|"floor"|"ceil"|"abs"|"clip"|"min"|"max"|"gt"|"ge"|"lt"|"le"|"eq"|"ne"|"and"|"or"|"not"|"if_else"|"is_null"|"not_null"|"coalesce"|"duration_hours"|"duration_seconds"|"time_of_day"|"date_of"|"day_of_week"|"add_days"|"add_hours"|"add_seconds","args":[Expr]}.
Constraint: {"operator":"unique"|"less_or_equal"|"not_null"|"in_set"|"range"|"implies_null","columns":[string],"values":[value],"minimum":number,"maximum":number,"description":string}.
Relationship: {"parent_table":string,"parent_key":string,"child_table":string,"child_key":string,"cardinality":"one_to_many"|"one_to_one","optional":boolean,"null_fraction":number,"child_count_min":integer,"child_count_max":integer}.'''


def _remove_unsupported_period_summaries(
    prompt: str, spec: SyntheticDataSpec
) -> tuple[list[str], list[str]]:
    """Never replace requested employee-period calculations with random numbers."""
    if not _period_summary_requested(prompt):
        return [], []
    removed = [table.name for table in spec.tables if _is_period_summary_name(table.name)]
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
            match = None
            for candidate in pattern.finditer(text):
                # Only a table *total* is enforced. The upper end of a range ("4 to 6
                # assessments", "between 5 and 40 results") or a per-parent count
                # ("each course has 6 assessments") is a children-per-parent bound, and
                # copying it into the table's total rows made every such request
                # infeasible after the model had proposed it correctly.
                before = text[max(0, candidate.start() - 80):candidate.start()]
                clause = re.split(r"[.;:\n]", before)[-1]
                is_range_end = re.search(r"\d[\d,]*\s*(to|and|or|-|–)\s*$", before)
                is_per_parent = re.search(r"\b(each|per|every)\b", clause)
                if not (is_range_end or is_per_parent):
                    match = candidate
                    break
            if match:
                break
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


def _reconcile_relationship_contract(
    spec: SyntheticDataSpec, explicit_rows: list[dict]
) -> list[str]:
    """Apply relationship facts that do not require organizational judgment.

    The model discovers the relationship. The platform owns the execution detail:
    relationship keys are never independently sampled, and an unspecified child-table
    total is derived from its declared children-per-parent bounds.
    """
    changes: list[str] = []
    explicit_tables = {item["table"] for item in explicit_rows}
    child_tables = {relationship.child_table for relationship in spec.relationships}
    for table_name in sorted(child_tables - explicit_tables):
        table = spec.table(table_name)
        if table is not None and table.rows is not None:
            table.rows = None
            changes.append(
                f"{table_name}.rows will be derived from its relationship bounds because the prompt did not state a total."
            )

    for relationship in spec.relationships:
        parent = spec.table(relationship.parent_table)
        child = spec.table(relationship.child_table)
        if parent is None or child is None:
            continue
        parent_column = parent.column(relationship.parent_key)
        child_column = child.column(relationship.child_key)
        if parent_column is None:
            continue
        if parent.primary_key is None:
            parent.primary_key = relationship.parent_key
            changes.append(
                f"{relationship.parent_table}.{relationship.parent_key} was declared as the parent primary key."
            )
        if parent_column.role != SemanticRole.IDENTIFIER:
            parent_column.role = SemanticRole.IDENTIFIER
            parent_column.formula = None
            changes.append(
                f"{relationship.parent_table}.{relationship.parent_key} was marked as an identifier."
            )
        if child_column is None:
            child.columns.append(
                Column(
                    name=relationship.child_key,
                    type=parent_column.type,
                    role=SemanticRole.FOREIGN_KEY,
                    nullable=relationship.optional,
                )
            )
            changes.append(
                f"{relationship.child_table}.{relationship.child_key} was added as a relationship-owned foreign key."
            )
            continue
        changed = (
            child_column.role != SemanticRole.FOREIGN_KEY
            or child_column.rule is not None
            or child_column.formula is not None
            or child_column.type != parent_column.type
        )
        child_column.role = SemanticRole.FOREIGN_KEY
        child_column.rule = None
        child_column.formula = None
        child_column.source_expression = None
        child_column.type = parent_column.type
        child_column.nullable = relationship.optional
        if changed:
            changes.append(
                f"{relationship.child_table}.{relationship.child_key} was made relationship-owned; its independent sampling rule was removed."
            )
    return changes


def _reconcile_executable_constraints(spec: SyntheticDataSpec) -> list[str]:
    """Convert declared checks into constructs the rules engine can actually satisfy."""
    changes: list[str] = []
    incoming = {
        table.name: [relationship for relationship in spec.relationships if relationship.child_table == table.name]
        for table in spec.tables
    }
    for table in spec.tables:
        supported_unique_keys: list[list[str]] = []
        for key in table.unique_keys:
            relationships = incoming[table.name]
            is_primary_key = len(key) == 1 and key[0] == table.primary_key
            is_junction_pair = (
                len(relationships) == 2
                and set(key) == {relationship.child_key for relationship in relationships}
            )
            only = table.column(key[0]) if len(key) == 1 else None
            is_unique_list = (
                only is not None and only.rule is not None and only.rule.kind.value == "choice"
            )
            if is_primary_key or is_junction_pair or is_unique_list:
                supported_unique_keys.append(key)
            else:
                changes.append(
                    f"{table.name} uniqueness on ({', '.join(key)}) was omitted because this engine only constructs primary-key uniqueness, unique value lists and compound-unique junction pairs; the generated primary key remains unique."
                )
        table.unique_keys = supported_unique_keys

        for constraint in table.constraints:
            if constraint.operator != ConstraintOperator.LESS_OR_EQUAL or len(constraint.columns) != 2:
                continue
            earlier, later = (table.column(name) for name in constraint.columns)
            if earlier is None or later is None:
                continue
            if earlier.type not in {ColumnType.DATE, ColumnType.TIMESTAMP}:
                continue
            if later.type not in {ColumnType.DATE, ColumnType.TIMESTAMP}:
                continue
            if later.role == SemanticRole.DERIVED:
                continue
            if later.role in {SemanticRole.IDENTIFIER, SemanticRole.FOREIGN_KEY}:
                continue
            later_name = later.name.lower()
            if earlier.type == ColumnType.TIMESTAMP or later.type == ColumnType.TIMESTAMP:
                operator = "add_hours"
                offset = 8 if "time_out" in later_name or "end_time" in later_name else 24
                unit = "hours"
            else:
                operator = "add_days"
                if "due" in later_name:
                    offset = 7
                elif "deadline" in later_name:
                    offset = 30
                elif "completion" in later_name:
                    offset = 30
                elif "submission" in later_name:
                    offset = 7
                else:
                    offset = 1
                unit = "days"
            later.role = SemanticRole.DERIVED
            later.rule = None
            later.formula = Expr(
                op=operator,
                args=[Expr(col=earlier.name), Expr(const=offset)],
            )
            changes.append(
                f"{table.name}.{later.name} is derived as {offset} {unit} after {earlier.name} so the declared date order is enforced. Review this synthetic timing assumption."
            )
    return changes


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
        # The schema alone was not enough: models guessed keys such as "table" or
        # "column" for these two lists and failed validation, so each gets a concrete
        # example in the same style as the rule example above.
        'A child value bounded by its parent uses cross_table_constraints, for example '
        '{"parent_table":"assessments","child_table":"results","child_key":"assessment_id",'
        '"parent_column":"maximum_score","child_column":"score_obtained","operator":"less_or_equal"} '
        '(read as child_column operator parent_column: score_obtained <= maximum_score). '
        'A parent column summarising its children uses aggregates, for example '
        '{"parent_table":"students","child_table":"results","child_key":"student_id",'
        '"target_column":"result_count","operation":"count"}; the target column must exist on the '
        'parent with role aggregate. '
        'Codes, names and other values that must not repeat get a unique constraint '
        '{"operator":"unique","columns":["course_code"]} and a choice list with at least as many values '
        'as rows; lists written in parallel with the same length (codes and their names) stay paired by position. '
        'A value that must be empty for some status uses {"operator":"implies_null",'
        '"columns":["submission_status","score_obtained"],"values":["missing"]}. '
        'Use derived only for a same-table formula. Use aggregate only for a supported direct-child '
        'count/sum/mean/min/max grouped by one parent key. The platform cannot compute employee-by-month '
        'or other entity-period summaries across several activity tables: omit such summary tables rather '
        'than inventing their measures as random rules. Same-table date ordering belongs in table constraints. '
        'Do not add entities the user did not request. Keep the JSON compact by omitting fields that use defaults. '
        +_compact_contract()
    )
    payload={'model':settings['model'], 'messages':[{'role':'system','content':instruction},{'role':'user','content':prompt}],
             'response_format':{'type':'json_object'},'reasoning_effort':settings['reasoning'],'max_completion_tokens':32768}
    if _repair is not None:
        payload['messages'].append(
            {'role':'user','content':'Regenerate the complete compact JSON proposal. The prior proposal was rejected: '+_repair[1]}
        )
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
        prepared, preparse_removed = _prepare_model_output(prompt, content)
        spec=SyntheticDataSpec.model_validate(prepared)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        structural_error = _schema_error_summary(exc)
        if _repair is None:
            prior = content[:12000] if isinstance(locals().get('content'), str) else '{}'
            first_failure = (
                f"provider finish reason: {finish_reason}; structural error: {structural_error}"
            )
            try:
                return propose(prompt, (prior, first_failure))
            except ValueError as repair_error:
                raise ValueError(
                    "The hosted model's first proposal was not executable "
                    f"({first_failure}). Its one correction attempt also failed: {repair_error}"
                ) from None
        raise ValueError(
            'The hosted model could not produce an executable specification after one correction attempt. '
            f'Last structural error (provider finish reason: {finish_reason}): {structural_error}. '
            'Try requesting the base entities first, then add relationships in the guided editor. '
            'Entity-period summaries across several activity tables are not supported yet.'
        ) from None
    if spec.mode.value not in ('schema_rules','relational_rules'):
        raise ValueError('The assistant may propose only scenarios without source records.')
    removed_tables, limitations = _remove_unsupported_period_summaries(prompt, spec)
    removed_tables = list(dict.fromkeys([*preparse_removed, *removed_tables]))
    explicit_rows = _enforce_explicit_row_requirements(prompt, spec)
    automatic_reconciliations = _reconcile_relationship_contract(spec, explicit_rows)
    automatic_reconciliations.extend(_reconcile_executable_constraints(spec))
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
                'automatic_reconciliations':automatic_reconciliations,
            }}
