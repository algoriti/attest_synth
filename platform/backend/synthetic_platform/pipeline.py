"""Orchestration: specification in, dataset plus evidence report out.

The order is fixed and matters:

    validate -> generate (modellable columns only) -> derive -> normalise
             -> check constraints -> evaluate -> report

Deriving after generation is what keeps computed columns consistent with the columns
they are computed from. Evaluating after everything is what keeps the generator out of
the business of grading itself.

Nothing in the report is allowed to imply a privacy guarantee. The `privacy` block
states what was and was not done, in the same words every time.
"""
from __future__ import annotations

import platform
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from . import __version__
from .derive import DerivationError, apply_derived
from .engines import base as engine_base
from .engines.relational import (
    RelationalRuleEngine,
    cardinality_report,
    referential_integrity,
)
from .evaluate import check_constraints, fidelity, predictive_utility
from .spec import Mode, SemanticRole, SyntheticDataSpec
from .suggest import prepare_source
from .validator import validate


class PipelineError(RuntimeError):
    def __init__(self, message: str, findings: list[dict] | None = None) -> None:
        super().__init__(message)
        self.findings = findings or []


def run(
    spec: SyntheticDataSpec,
    sources: dict[str, pd.DataFrame] | None = None,
    rows: int | None = None,
) -> dict:
    """Execute a specification end to end."""
    started = time.perf_counter()
    sources = sources or {}

    engine_name = engine_base.choose_engine(spec)
    engine = engine_base.get_engine(engine_name)
    capabilities = engine.capabilities()

    validation = validate(spec, capabilities)
    if not validation.ok:
        raise PipelineError(
            "The specification was rejected before generation.",
            [f.as_dict() for f in validation.errors],
        )

    if spec.is_relational:
        return _run_relational(spec, engine, validation, started, engine_name)

    table = spec.primary_table
    requested = rows or table.rows or 100
    source = sources.get(table.name)

    if spec.mode == Mode.LEARNED_TABLE and source is None:
        raise PipelineError(f"Mode 'learned_table' needs source records for '{table.name}'.")

    # Columns that declare a source expression are feature-engineered onto the source
    # before an engine sees it, so a rewritten specification trains on the columns it
    # actually declares rather than on whatever the upload happened to contain.
    if source is not None and any(c.source_expression for c in table.columns):
        try:
            source = prepare_source(source, table)
        except DerivationError as exc:
            raise PipelineError(f"Could not prepare the source columns: {exc}") from exc

    outcome = engine.generate(spec, table, requested, source)

    frame, derivation_trace = apply_derived(outcome.frame, table)
    outcome.frame = frame
    outcome.derivation_trace = derivation_trace

    constraint_results = check_constraints(frame, table)

    evaluation: dict = {}
    if source is not None:
        if "fidelity" in spec.evaluation.checks:
            evaluation["fidelity"] = fidelity(frame, source, table)
        if "predictive_utility" in spec.evaluation.checks and spec.evaluation.target:
            task = spec.evaluation.task or "classification"
            evaluation["predictive_utility"] = predictive_utility(
                frame, source, table, spec.evaluation.target, task, spec.seed
            )

    report = build_report(
        spec=spec,
        outcomes={table.name: outcome},
        constraint_results={table.name: constraint_results},
        evaluation=evaluation,
        validation_findings=[f.as_dict() for f in validation.findings],
        engine_name=engine_name,
        capabilities=capabilities,
        elapsed=time.perf_counter() - started,
    )
    return {"frames": {table.name: frame}, "report": report}


def _run_relational(
    spec: SyntheticDataSpec,
    engine,
    validation,
    started: float,
    engine_name: str,
) -> dict:
    if not isinstance(engine, RelationalRuleEngine):
        raise PipelineError(f"Engine '{engine_name}' cannot generate relational data.")

    outcomes = engine.generate_all(spec)
    frames: dict[str, pd.DataFrame] = {}
    constraint_results: dict[str, list[dict]] = {}

    for name, outcome in outcomes.items():
        table = spec.table(name)
        assert table is not None
        frame, trace = apply_derived(outcome.frame, table)
        outcome.frame = frame
        outcome.derivation_trace = trace
        frames[name] = frame
        constraint_results[name] = check_constraints(frame, table)

    evaluation = {
        "referential_integrity": referential_integrity(spec, frames),
        "cardinality": cardinality_report(spec, frames),
    }

    report = build_report(
        spec=spec,
        outcomes=outcomes,
        constraint_results=constraint_results,
        evaluation=evaluation,
        validation_findings=[f.as_dict() for f in validation.findings],
        engine_name=engine_name,
        capabilities=engine.capabilities(),
        elapsed=time.perf_counter() - started,
    )
    return {"frames": frames, "report": report}


def build_report(
    spec: SyntheticDataSpec,
    outcomes: dict,
    constraint_results: dict[str, list[dict]],
    evaluation: dict,
    validation_findings: list[dict],
    engine_name: str,
    capabilities: dict,
    elapsed: float,
) -> dict:
    """Assemble the evidence report.

    Completeness and repair counts sit at the top rather than in an appendix: a request
    for 10,000 rows answered with 8,000 is an incomplete result, and a column that was
    silently rounded into range is something a reader needs before they trust a number
    further down.
    """
    tables_block = []
    all_constraints_passed = True
    incomplete: list[str] = []

    for name, outcome in outcomes.items():
        checks = constraint_results.get(name, [])
        passed = all(c["passed"] for c in checks)
        all_constraints_passed &= passed
        if not outcome.complete:
            incomplete.append(name)

        table = spec.table(name)
        roles: dict[str, list[str]] = {}
        if table:
            for column in table.columns:
                roles.setdefault(column.role.value, []).append(column.name)

        tables_block.append(
            {
                "table": name,
                "requested_rows": outcome.requested_rows,
                "generated_rows": outcome.generated_rows,
                "complete": outcome.complete,
                "elapsed_seconds": round(outcome.elapsed_seconds, 4),
                "engine_settings": outcome.settings,
                "warnings": outcome.warnings,
                "repairs": {
                    "by_column": outcome.repairs,
                    "repaired_row_fraction": round(outcome.repaired_row_fraction, 6),
                    "raw_invalid_row_fraction": round(outcome.raw_invalid_row_fraction, 6),
                    "note": (
                        "Repairs are type and bound corrections applied by the platform "
                        "after generation. A high fraction often means one integer column "
                        "was returned as a float, not that the data is unusable."
                    ),
                },
                "derived_columns": outcome.derivation_trace,
                "column_roles": roles,
                "constraints": checks,
                "constraints_passed": passed,
            }
        )

    assumptions = spec.open_assumptions()

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "platform_version": __version__,
        "specification": {
            "name": spec.name,
            "spec_version": spec.spec_version,
            "mode": spec.mode.value,
            "purpose": spec.purpose.value,
            "seed": spec.seed,
        },
        "engine": {
            "selected": engine_name,
            "capabilities": capabilities,
            "note": "The platform, not the engine, performed validation and evaluation.",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "executable": sys.executable,
        },
        "summary": {
            "tables": len(outcomes),
            "total_rows": sum(o.generated_rows for o in outcomes.values()),
            "all_constraints_passed": all_constraints_passed,
            "incomplete_tables": incomplete,
            "open_assumptions": len(assumptions),
            "elapsed_seconds": round(elapsed, 4),
        },
        "tables": tables_block,
        "evaluation": evaluation,
        "validation": {
            "findings": validation_findings,
            "warnings": [f for f in validation_findings if f["severity"] == "warning"],
        },
        "assumptions": assumptions,
        "privacy": {
            "mechanism": spec.privacy.mechanism,
            "protected_entity": spec.privacy.protected_entity,
            "release_claim_permitted": False,
            "statement": (
                "This platform applies no formal privacy mechanism. Nothing in this report "
                "supports a claim that the output is anonymous or safe to release. In the "
                "benchmark behind this platform, a control that copied real training rows "
                "verbatim reached 0.291 average precision against real data's 0.306, so "
                "high utility and zero privacy are demonstrably compatible. Any release of "
                "data derived from real records needs a separate threat model and a "
                "disclosure decision."
            ),
        },
        "reproduction": {
            "seed": spec.seed,
            "note": (
                "Re-running this specification with the same seed, engine version and "
                "source data reproduces this dataset. Library and platform differences can "
                "still change floating-point results."
            ),
        },
    }
