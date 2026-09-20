"""Tests for the specification, validator, derivation, engines and pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthetic_platform.derive import DerivationError, apply_derived, derivation_order
from synthetic_platform.engines import available_engines, get_engine
from synthetic_platform.engines.relational import (
    RelationalRuleEngine,
    generation_order,
    referential_integrity,
)
from synthetic_platform.evaluate import check_constraints
from synthetic_platform.pipeline import PipelineError, run
from synthetic_platform.profile import profile_csv
from synthetic_platform.suggest import (
    apply_suggestions,
    prepare_source,
    suggest_for_table,
)
from synthetic_platform.spec import (
    Column,
    ColumnType,
    Constraint,
    ConstraintOperator,
    Evaluation,
    Expr,
    Mode,
    Origin,
    PrivacyIntent,
    Provenance,
    Purpose,
    Relationship,
    Rule,
    RuleKind,
    SemanticRole,
    SyntheticDataSpec,
    Table,
)
from synthetic_platform.validator import Severity, validate


# --- helpers ---------------------------------------------------------------------


def simple_table(**kwargs) -> Table:
    return Table(
        name="orders",
        rows=50,
        primary_key="order_id",
        columns=[
            Column(
                name="order_id",
                type=ColumnType.STRING,
                role=SemanticRole.IDENTIFIER,
                rule=Rule(kind=RuleKind.SEQUENCE, prefix="ORD-"),
            ),
            Column(
                name="quantity",
                type=ColumnType.INTEGER,
                role=SemanticRole.RULE,
                rule=Rule(kind=RuleKind.INTEGER_RANGE, start=1, end=10),
                minimum=1,
                maximum=10,
            ),
            Column(
                name="unit_price_cents",
                type=ColumnType.INTEGER,
                role=SemanticRole.RULE,
                rule=Rule(kind=RuleKind.INTEGER_RANGE, start=100, end=20000),
                minimum=100,
                maximum=20000,
            ),
            Column(
                name="total_cents",
                type=ColumnType.INTEGER,
                role=SemanticRole.DERIVED,
                formula=Expr.model_validate(
                    {"op": "mul", "args": [{"col": "quantity"}, {"col": "unit_price_cents"}]}
                ),
            ),
        ],
        constraints=[
            Constraint(operator=ConstraintOperator.UNIQUE, columns=["order_id"]),
            Constraint(
                operator=ConstraintOperator.PRODUCT_EQUALS,
                columns=["quantity", "unit_price_cents", "total_cents"],
            ),
        ],
        **kwargs,
    )


def simple_spec(**kwargs) -> SyntheticDataSpec:
    defaults = dict(
        name="orders_demo",
        mode=Mode.SCHEMA_RULES,
        purpose=Purpose.SOFTWARE_TESTING,
        tables=[simple_table()],
    )
    defaults.update(kwargs)
    return SyntheticDataSpec(**defaults)


# --- spec model ------------------------------------------------------------------


def test_derived_column_requires_formula():
    with pytest.raises(ValueError, match="needs a formula"):
        Column(name="x", type=ColumnType.INTEGER, role=SemanticRole.DERIVED)


def test_rule_column_requires_rule():
    with pytest.raises(ValueError, match="needs a rule"):
        Column(name="x", type=ColumnType.INTEGER, role=SemanticRole.RULE)


def test_expression_rejects_unknown_operator():
    with pytest.raises(ValueError, match="unknown operator"):
        Expr.model_validate({"op": "exec", "args": []})


def test_expression_needs_exactly_one_form():
    with pytest.raises(ValueError, match="exactly one"):
        Expr.model_validate({"op": "add", "col": "x"})


def test_minimum_above_maximum_is_rejected():
    with pytest.raises(ValueError, match="minimum above maximum"):
        Column(name="x", type=ColumnType.INTEGER, minimum=10, maximum=1)


def test_open_assumptions_lists_unconfirmed_claims():
    table = simple_table()
    table.columns[1].provenance = Provenance(
        origin=Origin.ASSISTANT_PROPOSED, detail="guessed range"
    )
    spec = simple_spec(tables=[table])
    assumptions = spec.open_assumptions()
    assert any(a["scope"] == "orders.quantity" for a in assumptions)


# --- validator -------------------------------------------------------------------


def test_valid_spec_passes():
    assert validate(simple_spec()).ok


def test_unknown_constraint_column_is_an_error():
    table = simple_table()
    table.constraints.append(
        Constraint(operator=ConstraintOperator.UNIQUE, columns=["nope"])
    )
    result = validate(simple_spec(tables=[table]))
    assert not result.ok
    assert any(f.code == "unknown_constraint_column" for f in result.errors)


def test_constraint_arity_is_enforced():
    table = simple_table()
    table.constraints.append(
        Constraint(operator=ConstraintOperator.PRODUCT_EQUALS, columns=["quantity"])
    )
    result = validate(simple_spec(tables=[table]))
    assert any(f.code == "constraint_arity" for f in result.errors)


def test_formula_referencing_unknown_column_is_rejected():
    table = simple_table()
    table.columns[3].formula = Expr.model_validate({"op": "mul", "args": [{"col": "ghost"}, {"const": 2}]})
    result = validate(simple_spec(tables=[table]))
    assert any(f.code == "formula_unknown_column" for f in result.errors)


def test_learned_column_without_source_is_rejected():
    table = simple_table()
    table.columns[1].role = SemanticRole.LEARNED
    result = validate(simple_spec(tables=[table]))
    assert any(f.code == "learned_without_source" for f in result.errors)


def test_release_claim_cannot_be_permitted():
    spec = simple_spec(privacy=PrivacyIntent(release_claim_permitted=True))
    result = validate(spec)
    assert any(f.code == "unsupported_release_claim" for f in result.errors)


def test_differential_privacy_is_rejected_because_unimplemented():
    spec = simple_spec(privacy=PrivacyIntent(mechanism="differential_privacy", epsilon=1.0))
    result = validate(spec)
    assert any(f.code == "dp_not_implemented" for f in result.errors)


def test_fidelity_without_source_is_rejected():
    spec = simple_spec(evaluation=Evaluation(checks=["fidelity"]))
    result = validate(spec)
    assert any(f.code == "fidelity_without_source" for f in result.errors)


def test_single_table_engine_cannot_accept_relational_request():
    spec = relational_spec()
    caps = get_engine("rules").capabilities()
    result = validate(spec, caps)
    assert any(f.code == "engine_lacks_multi_table" for f in result.errors)


def test_derivation_cycle_is_detected():
    table = simple_table()
    table.columns.append(
        Column(
            name="a",
            type=ColumnType.INTEGER,
            role=SemanticRole.DERIVED,
            formula=Expr.model_validate({"op": "add", "args": [{"col": "b"}]}),
        )
    )
    table.columns.append(
        Column(
            name="b",
            type=ColumnType.INTEGER,
            role=SemanticRole.DERIVED,
            formula=Expr.model_validate({"op": "add", "args": [{"col": "a"}]}),
        )
    )
    result = validate(simple_spec(tables=[table]))
    assert any(f.code == "derivation_cycle" for f in result.errors)


def test_sensitive_learned_column_warns():
    frame = pd.DataFrame({"salary": np.arange(100), "dept": ["a", "b"] * 50})
    table, _ = profile_csv(frame, "people")
    table.column("salary").sensitive = True
    spec = SyntheticDataSpec(
        name="people",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        tables=[table],
    )
    result = validate(spec)
    assert any(f.code == "sensitive_learned" for f in result.warnings)


# --- derivation ------------------------------------------------------------------


def test_derived_columns_are_computed_not_generated():
    frame = pd.DataFrame({"quantity": [2, 3], "unit_price_cents": [150, 200], "total_cents": [0, 0]})
    table = simple_table()
    result, trace = apply_derived(frame, table)
    assert result["total_cents"].tolist() == [300, 600]
    assert trace[0]["column"] == "total_cents"
    assert trace[0]["depends_on"] == ["quantity", "unit_price_cents"]


def test_derivation_order_respects_dependencies():
    table = Table(
        name="t",
        columns=[
            Column(name="base", type=ColumnType.INTEGER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.INTEGER_RANGE, start=1, end=5)),
            Column(name="second", type=ColumnType.INTEGER, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate({"op": "add", "args": [{"col": "first"}, {"const": 1}]})),
            Column(name="first", type=ColumnType.INTEGER, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate({"op": "add", "args": [{"col": "base"}, {"const": 1}]})),
        ],
    )
    assert [c.name for c in derivation_order(table)] == ["first", "second"]


def test_division_by_zero_is_reported_not_silenced():
    frame = pd.DataFrame({"a": [1.0], "b": [0.0], "c": [0.0]})
    table = Table(
        name="t",
        columns=[
            Column(name="a", type=ColumnType.NUMBER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.NUMBER_RANGE)),
            Column(name="b", type=ColumnType.NUMBER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.NUMBER_RANGE)),
            Column(name="c", type=ColumnType.NUMBER, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate({"op": "div", "args": [{"col": "a"}, {"col": "b"}]})),
        ],
    )
    with pytest.raises(DerivationError, match="division by zero"):
        apply_derived(frame, table)


def test_time_of_day_respects_timezone_offset():
    frame = pd.DataFrame({"t": pd.to_datetime(["2024-01-01T05:00:00Z"]), "late": [False]})
    table = Table(
        name="t",
        columns=[
            Column(name="t", type=ColumnType.TIMESTAMP, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.TIMESTAMP_RANGE)),
            Column(name="late", type=ColumnType.BOOLEAN, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate({
                       "op": "gt",
                       "args": [
                           {"op": "time_of_day", "args": [{"col": "t"}], "tz_offset_hours": 3.0},
                           {"const": 7.75},
                       ],
                   })),
        ],
    )
    result, _ = apply_derived(frame, table)
    # 05:00 UTC is 08:00 local, which is after the 07:45 cutoff.
    assert bool(result["late"].iloc[0]) is True


# --- engines and pipeline --------------------------------------------------------


def test_every_engine_declares_capabilities():
    for caps in available_engines():
        assert {"name", "multi_table", "learns_from_records", "schema_only"} <= set(caps)


def test_rules_pipeline_generates_and_passes_constraints():
    result = run(simple_spec(), rows=200)
    frame = result["frames"]["orders"]
    report = result["report"]

    assert len(frame) == 200
    assert report["summary"]["all_constraints_passed"]
    assert (frame["total_cents"] == frame["quantity"] * frame["unit_price_cents"]).all()
    assert frame["order_id"].is_unique


def test_report_states_no_privacy_guarantee():
    report = run(simple_spec(), rows=20)["report"]
    assert report["privacy"]["release_claim_permitted"] is False
    statement = report["privacy"]["statement"]
    assert "no formal privacy mechanism" in statement
    assert "Nothing in this report supports a claim" in statement


def test_row_count_is_reported_exactly():
    report = run(simple_spec(), rows=137)["report"]
    table_block = report["tables"][0]
    assert table_block["requested_rows"] == 137
    assert table_block["generated_rows"] == 137
    assert table_block["complete"] is True


def test_invalid_spec_is_rejected_before_generation():
    table = simple_table()
    table.constraints.append(Constraint(operator=ConstraintOperator.UNIQUE, columns=["ghost"]))
    with pytest.raises(PipelineError) as exc:
        run(simple_spec(tables=[table]), rows=10)
    assert any(f["code"] == "unknown_constraint_column" for f in exc.value.findings)


def test_identifiers_are_regenerated_not_copied():
    source = pd.DataFrame(
        {
            "user_id": [f"U{i}" for i in range(200)],
            "score": np.random.default_rng(0).integers(0, 100, 200),
            "grade": ["a", "b", "c", "d"] * 50,
        }
    )
    table, _ = profile_csv(source, "people")
    assert table.column("user_id").role == SemanticRole.IDENTIFIER

    spec = SyntheticDataSpec(
        name="people",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        engine="independent",
        tables=[table],
    )
    frame = run(spec, sources={"people": source}, rows=100)["frames"]["people"]
    assert not set(frame["user_id"]) & set(source["user_id"])


def test_seed_makes_generation_reproducible():
    a = run(simple_spec(seed=7), rows=50)["frames"]["orders"]
    b = run(simple_spec(seed=7), rows=50)["frames"]["orders"]
    pd.testing.assert_frame_equal(a, b)


# --- constraint checking ---------------------------------------------------------


def test_constraint_checker_detects_violations():
    frame = pd.DataFrame({"a": [1, 1], "b": [5, 1], "c": [5, 5]})
    table = Table(
        name="t",
        columns=[
            Column(name=n, type=ColumnType.INTEGER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.INTEGER_RANGE))
            for n in ("a", "b", "c")
        ],
        constraints=[
            Constraint(operator=ConstraintOperator.UNIQUE, columns=["a"]),
            Constraint(operator=ConstraintOperator.PRODUCT_EQUALS, columns=["a", "b", "c"]),
        ],
    )
    results = check_constraints(frame, table)
    assert results[0]["passed"] is False and results[0]["failing_rows"] == 1
    assert results[1]["passed"] is False and results[1]["failing_rows"] == 1


# --- profiling -------------------------------------------------------------------


def test_profiler_flags_empty_and_constant_columns():
    frame = pd.DataFrame(
        {"always_null": [None] * 100, "always_same": ["x"] * 100, "varies": list(range(100))}
    )
    table, report = profile_csv(frame, "t")
    assert table.column("always_null").role == SemanticRole.EMPTY
    assert table.column("always_same").role == SemanticRole.CONSTANT
    assert report["role_summary"]["empty"] == 1


def test_profiler_detects_product_relationship():
    rng = np.random.default_rng(3)
    quantity = rng.integers(1, 10, 300)
    price = rng.integers(100, 5000, 300)
    frame = pd.DataFrame(
        {"quantity": quantity, "unit_price": price, "total": quantity * price}
    )
    table, _ = profile_csv(frame, "orders")
    assert table.column("total").role == SemanticRole.DERIVED


def test_profiler_detects_null_flag_relationship():
    rng = np.random.default_rng(5)
    values = rng.normal(size=400)
    missing = rng.random(400) < 0.2
    frame = pd.DataFrame(
        {
            "measurement": np.where(missing, np.nan, values),
            "is_missing": missing,
            "other": rng.integers(0, 50, 400),
        }
    )
    table, _ = profile_csv(frame, "t")
    assert table.column("is_missing").role == SemanticRole.DERIVED


def test_profiler_applies_only_the_strongest_formula_per_column():
    rng = np.random.default_rng(11)
    quantity = rng.integers(1, 10, 300)
    price = rng.integers(100, 5000, 300)
    frame = pd.DataFrame(
        {"quantity": quantity, "unit_price": price, "total": quantity * price}
    )
    _, report = profile_csv(frame, "orders")
    applied = [n for n in report["notes"] if n.get("applied")]
    assert len({n["column"] for n in applied}) == len(applied)


# --- relational ------------------------------------------------------------------


def relational_spec() -> SyntheticDataSpec:
    employees = Table(
        name="employees",
        rows=25,
        primary_key="employee_id",
        columns=[
            Column(name="employee_id", type=ColumnType.STRING, role=SemanticRole.IDENTIFIER,
                   rule=Rule(kind=RuleKind.SEQUENCE, prefix="EMP-")),
            Column(name="department", type=ColumnType.CATEGORY, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.CHOICE, values=["ops", "finance", "it"])),
        ],
    )
    attendance = Table(
        name="attendance",
        primary_key="attendance_id",
        columns=[
            Column(name="attendance_id", type=ColumnType.UUID, role=SemanticRole.IDENTIFIER),
            Column(name="employee_id", type=ColumnType.STRING, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.SEQUENCE, prefix="TMP-")),
            Column(name="shift_hours", type=ColumnType.NUMBER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.NUMBER_RANGE, start=4, end=12, decimals=2)),
        ],
    )
    return SyntheticDataSpec(
        name="employee_relational",
        mode=Mode.RELATIONAL_RULES,
        purpose=Purpose.SOFTWARE_TESTING,
        engine="relational_rules",
        tables=[employees, attendance],
        relationships=[
            Relationship(
                parent_table="employees",
                parent_key="employee_id",
                child_table="attendance",
                child_key="employee_id",
                child_count_min=3,
                child_count_max=8,
            )
        ],
    )


def test_relational_generation_order_puts_parents_first():
    assert generation_order(relational_spec()) == ["employees", "attendance"]


def test_relational_generation_has_no_orphans():
    result = run(relational_spec())
    frames = result["frames"]
    assert set(frames) == {"employees", "attendance"}

    integrity = result["report"]["evaluation"]["referential_integrity"]
    assert integrity[0]["orphan_rows"] == 0
    assert integrity[0]["integrity"] == 1.0

    valid = set(frames["employees"]["employee_id"])
    assert set(frames["attendance"]["employee_id"]) <= valid


def test_relational_child_counts_respect_declared_range():
    frames = run(relational_spec())["frames"]
    counts = frames["attendance"].groupby("employee_id").size()
    assert counts.min() >= 3
    assert counts.max() <= 8


def test_relational_report_includes_cardinality():
    report = run(relational_spec())["report"]
    cardinality = report["evaluation"]["cardinality"]
    assert cardinality[0]["synthetic"]["parents"] == 25


def test_relationship_cycle_is_rejected():
    spec = relational_spec()
    spec.relationships.append(
        Relationship(
            parent_table="attendance",
            parent_key="attendance_id",
            child_table="employees",
            child_key="employee_id",
        )
    )
    result = validate(spec)
    assert any(f.code == "relationship_cycle" for f in result.errors)


def test_unknown_parent_table_is_rejected():
    spec = relational_spec()
    spec.relationships[0].parent_table = "ghost"
    result = validate(spec)
    assert any(f.code == "unknown_parent_table" for f in result.errors)


def test_referential_integrity_detects_injected_orphan():
    spec = relational_spec()
    frames = run(spec)["frames"]
    frames["attendance"].loc[0, "employee_id"] = "EMP-NOT-REAL"
    integrity = referential_integrity(spec, frames)
    assert integrity[0]["orphan_rows"] == 1


def test_profiler_detects_numeric_offset_rule():
    """A rule that survives feature engineering must still be found.

    Once timestamps become a `shift_hours` feature, "overtime = hours beyond a
    six-hour day" is a plain numeric relationship rather than a duration one.
    """
    rng = np.random.default_rng(17)
    shift_hours = np.round(rng.uniform(6.5, 16.0, 500), 3)
    frame = pd.DataFrame(
        {
            "shift_hours": shift_hours,
            "extra_hours": np.round(shift_hours - 6).astype(int),
            "noise": rng.integers(0, 90, 500),
        }
    )
    table, _ = profile_csv(frame, "shifts")
    assert table.column("extra_hours").role == SemanticRole.DERIVED


def test_profiler_detects_numeric_threshold_rule():
    rng = np.random.default_rng(23)
    clock_in = np.round(rng.uniform(4.0, 11.0, 500), 3)
    frame = pd.DataFrame(
        {
            "clock_in_hour": clock_in,
            "late_status": clock_in > 7.75,
            "noise": rng.integers(0, 90, 500),
        }
    )
    table, _ = profile_csv(frame, "shifts")
    assert table.column("late_status").role == SemanticRole.DERIVED


def test_derived_column_cannot_contradict_its_inputs():
    """The property the whole derived-column design exists to guarantee."""
    rng = np.random.default_rng(29)
    shift_hours = np.round(rng.uniform(6.5, 16.0, 400), 3)
    source = pd.DataFrame(
        {
            "shift_hours": shift_hours,
            "extra_hours": np.round(shift_hours - 6).astype(int),
        }
    )
    table, _ = profile_csv(source, "shifts")
    assert table.column("extra_hours").role == SemanticRole.DERIVED

    spec = SyntheticDataSpec(
        name="shifts",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        engine="independent",
        tables=[table],
    )
    frame = run(spec, sources={"shifts": source}, rows=300)["frames"]["shifts"]
    expected = np.clip(np.round(frame["shift_hours"] - 6), 0, None)
    assert (frame["extra_hours"] == expected).all()


# --- derived columns over incomplete inputs --------------------------------------


def _nullable_derived_table(nullable: bool) -> Table:
    """An integer column derived from a span whose end is sometimes missing."""
    return Table(
        name="sessions",
        columns=[
            Column(name="start", type=ColumnType.TIMESTAMP, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.TIMESTAMP_RANGE)),
            Column(name="end", type=ColumnType.TIMESTAMP, role=SemanticRole.RULE,
                   nullable=True, null_fraction=0.25,
                   rule=Rule(kind=RuleKind.TIMESTAMP_RANGE)),
            Column(
                name="extra_hours",
                type=ColumnType.INTEGER,
                role=SemanticRole.DERIVED,
                nullable=nullable,
                formula=Expr.model_validate(
                    {
                        "op": "round",
                        "args": [
                            {
                                "op": "sub",
                                "args": [
                                    {"op": "duration_hours", "args": [{"col": "start"}, {"col": "end"}]},
                                    {"const": 6},
                                ],
                            }
                        ],
                    }
                ),
            ),
        ],
    )


def _frame_with_open_session() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "start": pd.to_datetime(["2026-01-01T05:00:00Z", "2026-01-02T05:00:00Z"]),
            "end": pd.to_datetime(["2026-01-01T17:00:00Z", None]),
            "extra_hours": [0, 0],
        }
    )


def test_uncomputable_integer_formula_reports_the_cause():
    """A missing input must not surface as a pandas cast failure.

    Regression: an unclosed session leaves `end` null, the duration is NaN, and
    int64 cannot hold it. The old code raised IntCastingNaNError from deep inside
    pandas, naming neither the column nor the input responsible.
    """
    with pytest.raises(DerivationError) as exc:
        apply_derived(_frame_with_open_session(), _nullable_derived_table(nullable=False))

    message = str(exc.value)
    assert "extra_hours" in message
    assert "not nullable" in message
    assert "end" in message  # names the input that caused it


def test_nullable_derived_integer_keeps_the_gap():
    result, _ = apply_derived(_frame_with_open_session(), _nullable_derived_table(nullable=True))
    assert str(result["extra_hours"].dtype) == "Int64"
    assert result["extra_hours"].isna().sum() == 1
    assert result["extra_hours"].iloc[0] == 6


def test_uncomputable_boolean_formula_is_not_silently_true():
    """NaN is truthy, so astype(bool) would turn every uncomputable row into True."""
    table = Table(
        name="t",
        columns=[
            Column(name="value", type=ColumnType.NUMBER, role=SemanticRole.RULE,
                   nullable=True, rule=Rule(kind=RuleKind.NUMBER_RANGE)),
            Column(name="flag", type=ColumnType.BOOLEAN, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate(
                       {"op": "coalesce", "args": [{"col": "value"}]})),
        ],
    )
    frame = pd.DataFrame({"value": [1.0, None], "flag": [False, False]})
    with pytest.raises(DerivationError, match="flag"):
        apply_derived(frame, table)


def test_infinite_derived_value_is_rejected():
    table = Table(
        name="t",
        columns=[
            Column(name="a", type=ColumnType.NUMBER, role=SemanticRole.RULE,
                   rule=Rule(kind=RuleKind.NUMBER_RANGE)),
            Column(name="b", type=ColumnType.NUMBER, role=SemanticRole.DERIVED,
                   formula=Expr.model_validate({"op": "mul", "args": [{"col": "a"}, {"const": 1e308}]})),
        ],
    )
    frame = pd.DataFrame({"a": [1e308], "b": [0.0]})
    with pytest.raises(DerivationError, match="infinite"):
        apply_derived(frame, table)


def test_profiler_marks_a_gappy_formula_nullable():
    """The profiler must test its own proposals against the source."""
    rng = np.random.default_rng(41)
    start = pd.to_datetime("2026-01-01T05:00:00Z") + pd.to_timedelta(
        rng.integers(0, 500, 400), unit="D"
    )
    duration = rng.integers(7, 18, 400)
    end = start + pd.to_timedelta(duration, unit="h")
    end = pd.Series(end)
    end.iloc[:20] = pd.NaT  # unclosed sessions

    frame = pd.DataFrame(
        {
            "start": start,
            "end": end,
            "extra_hours": (duration - 6).astype(int),
        }
    )
    table, report = profile_csv(frame, "sessions")
    extra = table.column("extra_hours")
    assert extra.role == SemanticRole.DERIVED
    assert extra.nullable is True
    assert any(n["kind"] == "formula_gap" for n in report["notes"])

    # And the proposal it just verified must actually run.
    result, _ = apply_derived(frame, table)
    assert result["extra_hours"].isna().sum() == 20


def test_engine_rejects_column_types_it_cannot_model():
    """Unsupported input must fail at validation, not deep inside an engine.

    Regression: raw timestamp columns were handed to the tree-based engine, which
    declares no support for them. The request ran for minutes before failing.
    """
    frame = pd.DataFrame(
        {
            "when": pd.date_range("2026-01-01", periods=120, freq="h"),
            "amount": np.arange(120, dtype=float),
        }
    )
    table, _ = profile_csv(frame, "events")
    assert table.column("when").type == ColumnType.TIMESTAMP

    spec = SyntheticDataSpec(
        name="events",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        engine="arf",
        tables=[table],
    )
    result = validate(spec, get_engine("arf").capabilities())
    assert not result.ok
    finding = next(f for f in result.errors if f.code == "unsupported_column_type")
    assert "when" in finding.scope
    assert "timestamp" in finding.message


def test_capability_check_ignores_columns_the_engine_never_sees():
    """A derived timestamp is computed by the platform, so it is not the engine's problem."""
    table = Table(
        name="events",
        columns=[
            Column(name="amount", type=ColumnType.NUMBER, role=SemanticRole.LEARNED),
            Column(
                name="when",
                type=ColumnType.TIMESTAMP,
                role=SemanticRole.DERIVED,
                formula=Expr.model_validate(
                    {"op": "add_hours", "args": [{"col": "anchor"}, {"col": "amount"}]}
                ),
            ),
            Column(name="anchor", type=ColumnType.TIMESTAMP, role=SemanticRole.CONSTANT,
                   constant_value="2026-01-01T00:00:00Z"),
        ],
        source={"kind": "uploaded_csv"},
    )
    spec = SyntheticDataSpec(
        name="events",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        engine="arf",
        tables=[table],
    )
    result = validate(spec, get_engine("arf").capabilities())
    assert not any(f.code == "unsupported_column_type" for f in result.errors)


# --- suggested rewrites for unsupported columns -----------------------------------


def _temporal_source(with_time: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 300
    start = pd.Timestamp("2026-03-04", tz="UTC")  # a Wednesday
    offsets = rng.integers(0, 60, n)
    stamps = start + pd.to_timedelta(offsets, unit="D")
    if with_time:
        stamps = stamps + pd.to_timedelta(rng.integers(4 * 60, 11 * 60, n), unit="min")
    return pd.DataFrame({"when": stamps, "amount": rng.normal(50, 8, n).round(3)})


def test_suggestion_offered_only_for_unsupported_columns():
    table, _ = profile_csv(_temporal_source(), "events")
    caps = get_engine("arf").capabilities()
    suggestions = suggest_for_table(table, caps, 0.0, _temporal_source())

    assert [s.column for s in suggestions] == ["when"]
    assert suggestions[0].kind == "temporal_features"


def test_no_suggestion_when_the_engine_supports_everything():
    table, _ = profile_csv(_temporal_source(), "events")
    caps = get_engine("independent").capabilities()
    assert suggest_for_table(table, caps, 0.0) == []


def test_applied_suggestion_clears_the_validation_error():
    source = _temporal_source()
    table, _ = profile_csv(source, "events")
    caps = get_engine("arf").capabilities()

    spec = SyntheticDataSpec(
        name="events", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="arf", tables=[table],
    )
    assert any(f.code == "unsupported_column_type" for f in validate(spec, caps).errors)

    spec.tables[0] = apply_suggestions(table, suggest_for_table(table, caps, 0.0, source))
    assert not any(f.code == "unsupported_column_type" for f in validate(spec, caps).errors)


def test_suggestion_is_never_applied_without_being_accepted():
    source = _temporal_source()
    table, _ = profile_csv(source, "events")
    caps = get_engine("arf").capabilities()
    suggestions = suggest_for_table(table, caps, 0.0, source)

    untouched = apply_suggestions(table, suggestions, accept=set())
    assert untouched.column("when").role == SemanticRole.LEARNED
    assert untouched.column("when_hour") is None


def test_suggested_columns_are_marked_as_unconfirmed_assumptions():
    """A hardcoded default is still a claim the user did not make."""
    source = _temporal_source()
    table, _ = profile_csv(source, "events")
    caps = get_engine("arf").capabilities()
    rewritten = apply_suggestions(table, suggest_for_table(table, caps, 0.0, source))

    spec = SyntheticDataSpec(
        name="events", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="arf", tables=[rewritten],
    )
    scopes = {a["scope"] for a in spec.open_assumptions()}
    assert "events.when_hour" in scopes
    assert all(
        a["origin"] == "assistant_proposed"
        for a in spec.open_assumptions()
        if a["scope"].endswith(("_hour", "_weekday", "_anchor"))
    )


def test_date_column_gets_no_hour_feature():
    """A date sits at midnight, so an extracted hour would be constant.

    Regression: arfpy fits a truncated normal per numeric column and fails with a
    scipy domain error when the scale is zero.
    """
    frame = _temporal_source(with_time=False)
    table, _ = profile_csv(frame, "events")
    assert table.column("when").type == ColumnType.DATE

    caps = get_engine("arf").capabilities()
    suggestion = suggest_for_table(table, caps, 0.0, frame)[0]
    added = {c.name for c in suggestion.adds}
    assert "when_weekday" in added
    assert "when_hour" not in added

    prepared = prepare_source(frame, apply_suggestions(table, [suggestion]))
    assert prepared["when_weekday"].std() > 0


def test_rewritten_spec_generates_and_rebuilds_the_timestamp():
    source = _temporal_source()
    table, _ = profile_csv(source, "events")
    caps = get_engine("arf").capabilities()
    rewritten = apply_suggestions(table, suggest_for_table(table, caps, 0.0, source))

    spec = SyntheticDataSpec(
        name="events", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="independent", seed=3, tables=[rewritten],
    )
    frame = run(spec, sources={"events": source}, rows=120)["frames"]["events"]

    assert len(frame) == 120
    rebuilt = pd.to_datetime(frame["when"], utc=True)
    assert rebuilt.notna().all()
    # Every rebuilt value falls inside the one anchor week.
    span = (rebuilt.max() - rebuilt.min()).total_seconds() / 86400
    assert span <= 7


def test_source_expression_features_are_materialised():
    source = _temporal_source()
    table, _ = profile_csv(source, "events")
    caps = get_engine("arf").capabilities()
    rewritten = apply_suggestions(table, suggest_for_table(table, caps, 0.0, source))

    assert "when_hour" not in source.columns
    prepared = prepare_source(source, rewritten)
    assert "when_hour" in prepared.columns
    assert prepared["when_hour"].between(0, 24).all()
    assert prepared["when_weekday"].between(0, 6).all()


# --- cardinality ceiling ----------------------------------------------------------


def test_high_cardinality_category_is_rejected():
    """A supported type can still be unusable at scale.

    Regression: a string column with tens of thousands of levels passed the type
    check and then ran for minutes inside arfpy's categorical model.
    """
    table = Table(
        name="t",
        columns=[
            Column(
                name="email",
                type=ColumnType.CATEGORY,
                role=SemanticRole.LEARNED,
                allowed_values=[f"user{i}@example.com" for i in range(5000)],
            )
        ],
        source={"kind": "uploaded_csv"},
    )
    spec = SyntheticDataSpec(
        name="t", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="arf", tables=[table],
    )
    result = validate(spec, get_engine("arf").capabilities())
    finding = next(f for f in result.errors if f.code == "too_many_category_levels")
    assert "5,000" in finding.message
    assert "1,000" in finding.message


def test_cardinality_ceiling_ignores_identifiers():
    """Identifiers are regenerated, so their level count never reaches the engine."""
    table = Table(
        name="t",
        columns=[
            Column(
                name="user_id",
                type=ColumnType.CATEGORY,
                role=SemanticRole.IDENTIFIER,
                allowed_values=[f"U{i}" for i in range(5000)],
            ),
            Column(name="score", type=ColumnType.NUMBER, role=SemanticRole.LEARNED),
        ],
        source={"kind": "uploaded_csv"},
    )
    spec = SyntheticDataSpec(
        name="t", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="arf", tables=[table],
    )
    result = validate(spec, get_engine("arf").capabilities())
    assert not any(f.code == "too_many_category_levels" for f in result.errors)


# --- arfpy leaf degeneracy --------------------------------------------------------


def test_leaf_degeneracy_is_translated_into_an_actionable_error():
    """SciPy's bare domain error names neither the library, the column nor the cause."""
    from synthetic_platform.engines.learned import (
        ArfLeafDegeneracyError,
        _translate_arf_failure,
    )

    frame = pd.DataFrame({"flag": [1, 1, 1, 2], "value": [1.0, 2.0, 3.0, 4.0]})
    translated = _translate_arf_failure(
        ValueError("Domain error in arguments. The `scale` parameter must be positive"),
        frame,
        5,
    )
    assert isinstance(translated, ArfLeafDegeneracyError)
    message = str(translated)
    assert "min_node_size=5" in message
    assert "'flag' (2 distinct)" in message  # names the likeliest culprit


def test_unrelated_engine_errors_are_not_disguised():
    from synthetic_platform.engines.learned import _translate_arf_failure

    original = ValueError("something else entirely")
    assert _translate_arf_failure(original, pd.DataFrame({"a": [1]}), 5) is original


def test_engine_escalates_leaf_size_and_reports_the_retry(monkeypatch):
    """A degenerate leaf is recovered from, not surrendered to — and it is disclosed.

    Regression: on the attendance features arfpy succeeded at 8,000 rows and raised a
    bare SciPy domain error at 16,000. Coarsening the leaves fixes it, so the adapter
    escalates rather than failing, and records that it had to.
    """
    from synthetic_platform.engines import learned as learned_module

    attempts: list[int] = []

    class FakeArf:
        def __init__(self, frame, **kwargs):
            attempts.append(kwargs["min_node_size"])
            self._frame = frame
            self.acc = [0.5]

        def forde(self):
            if attempts[-1] < 20:  # the small leaf size is the one that fails
                raise ValueError(
                    "Domain error in arguments. The `scale` parameter must be positive"
                )

        def forge(self, n):
            return pd.DataFrame(
                {c: self._frame[c].head(1).repeat(n).to_numpy() for c in self._frame}
            )

    # The adapter imports arfpy inside generate(), so patching the module attribute
    # is enough to stand in for the real forest.
    import arfpy.arf as arf_module

    monkeypatch.setattr(arf_module, "arf", FakeArf)

    source = pd.DataFrame({"amount": np.linspace(0, 10, 60), "grade": ["a", "b"] * 30})
    table, _ = profile_csv(source, "t")
    spec = SyntheticDataSpec(
        name="t", mode=Mode.LEARNED_TABLE, purpose=Purpose.ML_DEVELOPMENT,
        engine="arf", tables=[table],
    )
    outcome = learned_module.ArfEngine().generate(spec, table, 10, source)

    assert attempts == [5, 20]
    assert outcome.settings["min_node_size"] == 20
    assert any("retried with 20" in w for w in outcome.warnings)


def test_leaf_size_ladder_only_coarsens():
    from synthetic_platform.engines.learned import ArfEngine

    ladder = list(ArfEngine.leaf_size_ladder)
    assert ladder == sorted(ladder) and len(set(ladder)) == len(ladder)
