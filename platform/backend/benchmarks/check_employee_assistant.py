"""Exercise the difficult employee prompt and record requirement-level evidence.

Credentials are read by ``synthetic_platform.assistant`` and are never serialized.
The benchmark sends only the text fixture and the public specification schema.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from synthetic_platform.assistant import configuration, propose
from synthetic_platform.pipeline import run
from synthetic_platform.spec import SyntheticDataSpec


PROMPT = HERE / "prompts" / "employee_behavioral_500_12_months.txt"
OUTPUT = HERE / "results" / "assistant_employee_behavioral_check.json"

REQUESTED_FIELDS = {
    "employees": {"employee_id", "department", "role", "grade", "employment_status", "hire_date"},
    "attendance": {"attendance_date", "time_in", "time_out", "lateness_status", "overtime_hours", "attendance_status"},
    "projects": {"complexity", "priority"},
    "project_assignments": {"assigned_date", "deadline", "completion_date", "assignment_status", "contribution_percentage"},
    "tasks": {"assigned_date", "deadline", "completion_date", "complexity", "status", "quality_score", "rework_count"},
    "reports": {"required_date", "due_date", "submission_date", "submission_status", "quality_score"},
}


def _normalized(value: str) -> str:
    return value.lower().strip().replace(" ", "_")


started = time.perf_counter()
try:
    answer = propose(PROMPT.read_text())
    spec = SyntheticDataSpec.model_validate(answer["spec"])
    generated = run(spec)
    tables = {_normalized(table.name): table for table in spec.tables}
    requested_entities = set(REQUESTED_FIELDS)
    missing_entities = sorted(requested_entities - set(tables))
    extra_entities = sorted(set(tables) - requested_entities)
    missing_fields = {
        table_name: sorted(fields - {_normalized(column.name) for column in tables[table_name].columns})
        for table_name, fields in REQUESTED_FIELDS.items()
        if table_name in tables and fields - {_normalized(column.name) for column in tables[table_name].columns}
    }
    employees = tables.get("employees")
    relationship_columns = {
        (relationship.child_table, relationship.child_key)
        for relationship in spec.relationships
    }
    bad_foreign_keys = sorted(
        f"{table}.{key}"
        for table, key in relationship_columns
        if (column := spec.table(table).column(key)) is None
        or column.role.value != "foreign_key"
        or column.rule is not None
    )
    report = {
        "model": configuration()["model"],
        "provider": "Groq",
        "status": "completed",
        "seconds": round(time.perf_counter() - started, 3),
        "requirement_checks": {
            "employees_requested": 500,
            "employees_specified": employees.rows if employees else None,
            "requested_entities_present": not missing_entities,
            "missing_entities": missing_entities,
            "extra_entities": extra_entities,
            "missing_requested_fields": missing_fields,
            "relationship_count": len(spec.relationships),
            "relationship_foreign_keys_are_owned": not bad_foreign_keys,
            "bad_foreign_keys": bad_foreign_keys,
            "unsupported_period_summary_disclosed": bool(answer["review"]["unsupported_requests"]),
            "period_summary_omitted_instead_of_randomized": not any(
                "summary" in name or "monthly" in name for name in tables
            ),
            "correction_attempted": answer["review"]["correction_attempted"],
        },
        "proposal_review": answer["review"],
        "generated_summary": generated["report"]["summary"],
        "generated_rows": {name: len(frame) for name, frame in generated["frames"].items()},
        "data_sent": "Prompt fixture and specification JSON schema only; no uploaded or private records.",
        "spec": answer["spec"],
    }
except Exception as exc:
    report = {
        "model": configuration()["model"],
        "provider": "Groq",
        "status": "failed",
        "seconds": round(time.perf_counter() - started, 3),
        "error": str(exc),
        "data_sent": "Prompt fixture and specification JSON schema only; no uploaded or private records.",
    }

OUTPUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
print(json.dumps({key: value for key, value in report.items() if key != "spec"}, indent=2))
if report["status"] == "failed":
    sys.exit(1)
