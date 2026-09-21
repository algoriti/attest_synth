"""Real-file acceptance check for the privacy-preserving upload assistant.

The source records stay inside this process. Groq receives only ``schema_manifest``
plus the prompt. The saved result contains no previews, hashes, upload identifiers,
record values, category values, or source file name.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

from synthetic_platform.api import app
from synthetic_platform.assistant import configuration, revise_uploaded_spec
from synthetic_platform.pipeline import run
from synthetic_platform.spec import SyntheticDataSpec

SOURCE = Path("/home/administrator/Documents/Attendance.csv")
PROMPT = HERE / "prompts" / "attendance_upload_revision.txt"
OUTPUT = HERE / "results" / "attendance_upload_revision_check.json"


def expression_columns(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        found = {value["col"]} if isinstance(value.get("col"), str) else set()
        for child in value.values():
            found |= expression_columns(child)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found |= expression_columns(child)
        return found
    return set()


def main() -> int:
    started = time.perf_counter()
    with TestClient(app) as client, SOURCE.open("rb") as handle:
        upload = client.post(
            "/api/upload", files={"file": ("attendance.csv", handle, "text/csv")}
        )
    upload.raise_for_status()
    payload = upload.json()
    table = payload["proposed_table"]
    has_learnable = any(column["role"] == "learned" for column in table["columns"])
    base = SyntheticDataSpec.model_validate(
        {
            "spec_version": "2.0",
            "name": table["name"],
            "mode": "learned_table" if has_learnable else "schema_rules",
            "purpose": "ml_development",
            "description": "Privacy-controlled attendance upload acceptance check",
            "engine": "independent" if has_learnable else "rules",
            "seed": 2026,
            "tables": [table],
            "relationships": [],
            "privacy": {
                "protected_entity": "employee",
                "mechanism": "none",
                "release_claim_permitted": False,
                "notes": "No formal privacy mechanism is applied.",
            },
            "evaluation": {"checks": ["schema", "constraints", "fidelity"]},
        }
    )

    answer = revise_uploaded_spec(PROMPT.read_text(), base)
    revised = SyntheticDataSpec.model_validate(answer["spec"])
    original_names = {column.name for column in base.primary_table.columns}
    added = [column for column in revised.primary_table.columns if column.name not in original_names]

    source = pd.read_csv(SOURCE, low_memory=False)
    generated = run(revised, sources={revised.primary_table.name: source}, rows=2000)
    frame = generated["frames"][revised.primary_table.name]
    failed_checks = [
        {key: value for key, value in check.items() if key != "detail"}
        for block in generated["report"]["tables"]
        for check in block["constraints"] if not check["passed"]
    ]
    semantic_checks = []
    for name in ("shift_duration_hours", "shift_duration_minutes", "overtime_hours", "early_exit_minutes"):
        if name in frame:
            numeric=pd.to_numeric(frame[name],errors="coerce")
            semantic_checks.append({
                "column":name,
                "check":"non_negative",
                "passed":bool((numeric.dropna() >= 0).all()),
                "failing_rows":int((numeric.dropna() < 0).sum()),
            })

    performance_words = ("performance", "productivity", "quality", "effectiveness", "reliability")
    added_evidence = []
    leakage_flags = []
    for column in added:
        dumped = column.model_dump(mode="json")
        refs = sorted(expression_columns(dumped.get("formula")))
        is_performance = any(word in column.name.lower() for word in performance_words)
        if is_performance and column.role.value == "derived":
            leakage_flags.append(
                f"{column.name} is constructed from {', '.join(refs) or 'other generated fields'}; "
                "using it as an ML target would encode the answer in its inputs."
            )
        added_evidence.append(
            {
                "name": column.name,
                "type": column.type.value,
                "role": column.role.value,
                "nullable": column.nullable,
                "formula_references": refs,
                "formula": dumped.get("formula"),
                "rule_kind": column.rule.kind.value if column.rule else None,
                "provenance_origin": column.provenance.origin.value,
                "provenance_detail": column.provenance.detail,
                "generated_non_null_fraction": round(float(frame[column.name].notna().mean()), 4),
                "generated_distinct_count": int(frame[column.name].nunique(dropna=True)),
            }
        )

    quality = payload["profile"].get("quality", [])
    result = {
        "status": "completed" if generated["report"]["summary"]["all_constraints_passed"] and all(c["passed"] for c in semantic_checks) else "evidence_failed",
        "provider": "Groq",
        "model": configuration()["model"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "privacy_check": {
            "sent_to_provider": "User instruction plus dataset/table names and column name, type, role, and nullability only.",
            "excluded": answer["disclosure"]["excluded"],
            "manifest_matches_platform_disclosure": answer["disclosure"]["manifest"] == {
                "dataset": base.name,
                "mode": base.mode.value,
                "tables": [{
                    "name": base.primary_table.name,
                    "primary_key": base.primary_table.primary_key,
                    "columns": [{
                        "name": c.name, "type": c.type.value,
                        "role": c.role.value, "nullable": c.nullable,
                    } for c in base.primary_table.columns],
                }],
            },
        },
        "source_summary_local_only": {
            "rows": int(payload["profile"]["rows"]),
            "columns": int(payload["profile"]["columns"]),
            "profile_quality_issue_count": len(quality),
            "profile_quality_issue_kinds": sorted({item.get("kind", "unspecified") for item in quality}),
        },
        "proposal": {
            "changes": answer["changes"],
            "assumptions": answer["assumptions"],
            "added_columns": added_evidence,
            "validation_ok": answer["validation"]["ok"],
        },
        "execution": {
            "engine": "independent",
            "generated_rows": len(frame),
            "generated_columns": list(frame.columns),
            "all_constraints_passed": generated["report"]["summary"]["all_constraints_passed"],
            "failed_checks": failed_checks,
            "semantic_checks": semantic_checks,
            "open_assumption_count": len(revised.open_assumptions()),
        },
        "ml_review": {
            "suitable_for": [
                "synthetic-data platform and pipeline testing",
                "exploratory time-behavior feature engineering",
                "demonstrating schema, provenance, and generation workflows",
            ],
            "not_supported_for": [
                "training or validating a real employee-performance predictor",
                "employment decisions or employee ranking",
                "causal claims about attendance and performance",
            ],
            "target_leakage_flags": leakage_flags,
            "missing_evidence": [
                "verified task and project outcomes",
                "quality, rework, and reporting measures",
                "a defined and independently observed performance target",
                "an entity-aware or time-based holdout evaluation for that target",
                "a formal privacy guarantee",
            ],
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
