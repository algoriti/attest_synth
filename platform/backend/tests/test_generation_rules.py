"""Unique value lists and status-driven empty values, independent of domain."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthetic_platform.pipeline import PipelineError, run
from synthetic_platform.spec import SyntheticDataSpec
from synthetic_platform.validator import validate

CODES = [f"C{i:03d}" for i in range(12)]
NAMES = [f"Name {i}" for i in range(12)]


def _table_spec(columns, constraints, rows=12):
    return SyntheticDataSpec.model_validate({
        "name": "t", "mode": "schema_rules", "purpose": "software_testing", "seed": 3,
        "tables": [{"name": "items", "rows": rows, "primary_key": "id",
                    "columns": [{"name": "id", "type": "integer", "role": "identifier"}, *columns],
                    "constraints": constraints}],
    })


def _unique_pair_spec(rows=12):
    return _table_spec(
        [{"name": "code", "type": "string", "role": "rule", "rule": {"kind": "choice", "values": CODES}},
         {"name": "label", "type": "string", "role": "rule", "rule": {"kind": "choice", "values": NAMES}}],
        [{"operator": "unique", "columns": ["code"]}, {"operator": "unique", "columns": ["label"]}],
        rows,
    )


def test_unique_list_values_never_repeat():
    """Regression: 12 course codes drawn from a 12-item list repeated 5 times."""
    frame = run(_unique_pair_spec())["frames"]["items"]
    assert frame["code"].is_unique and frame["label"].is_unique


def test_parallel_lists_stay_paired_by_position():
    """A code and its name, listed in the same order, stay together."""
    frame = run(_unique_pair_spec())["frames"]["items"]
    for code, label in zip(frame["code"], frame["label"]):
        assert CODES.index(code) == NAMES.index(label)


def test_unique_list_shorter_than_rows_is_rejected_before_generation():
    result = validate(_unique_pair_spec(rows=20))
    assert any(f.code == "unique_list_too_short" for f in result.errors)


def _status_spec(nullable=True, values=("missing",)):
    constraint = {"operator": "implies_null", "columns": ["status", "score"]}
    if values:
        constraint["values"] = list(values)
    return _table_spec(
        [{"name": "status", "type": "category", "role": "rule",
          "rule": {"kind": "choice", "values": ["submitted", "late", "missing"]}},
         {"name": "score", "type": "integer", "role": "rule", "nullable": nullable,
          "rule": {"kind": "integer_range", "start": 0, "end": 100}},
         {"name": "double_score", "type": "integer", "role": "derived", "nullable": True,
          "formula": {"op": "mul", "args": [{"col": "score"}, {"const": 2}]}}],
        [constraint], rows=300,
    )


def test_status_empties_its_dependent_value():
    """Regression: every 'missing' submission still carried a score."""
    result = run(_status_spec())
    frame = result["frames"]["items"]
    missing = frame["status"] == "missing"
    assert missing.any()
    assert frame.loc[missing, "score"].isna().all()
    assert frame.loc[~missing, "score"].notna().all()
    # A formula reading the emptied value is recomputed rather than left stale.
    assert frame.loc[missing, "double_score"].isna().all()
    assert result["report"]["summary"]["all_constraints_passed"]


def test_a_text_status_is_not_treated_as_true():
    """Regression: casting 'submitted' to bool made every non-empty status count as true."""
    frame = run(_status_spec())["frames"]["items"]
    assert frame.loc[frame["status"] == "submitted", "score"].notna().all()


def test_empty_value_rules_are_validated():
    no_values = validate(_status_spec(values=()))
    assert any(f.code == "implies_null_condition" for f in no_values.errors)
    not_nullable = validate(_status_spec(nullable=False))
    assert any(f.code == "implies_null_target_not_nullable" for f in not_nullable.errors)


def test_required_empty_value_does_not_fail_a_cross_table_rule():
    """Regression: 'no score for a missing submission' made 'score <= maximum' fail on
    every missing submission, so two declared rules contradicted each other."""
    spec = SyntheticDataSpec.model_validate({
        "name": "t", "mode": "relational_rules", "purpose": "software_testing",
        "engine": "relational_rules", "seed": 5,
        "tables": [
            {"name": "tests", "rows": 10, "primary_key": "tid", "columns": [
                {"name": "tid", "type": "integer", "role": "identifier"},
                {"name": "maximum", "type": "integer", "role": "rule",
                 "rule": {"kind": "choice", "values": [10, 20, 50]}}]},
            {"name": "results", "primary_key": "rid", "columns": [
                {"name": "rid", "type": "integer", "role": "identifier"},
                {"name": "tid", "type": "integer", "role": "foreign_key"},
                {"name": "status", "type": "category", "role": "rule",
                 "rule": {"kind": "choice", "values": ["submitted", "missing"]}},
                {"name": "score", "type": "integer", "role": "rule", "nullable": True,
                 "rule": {"kind": "integer_range", "start": 0, "end": 100}}],
             "constraints": [{"operator": "implies_null", "columns": ["status", "score"],
                              "values": ["missing"]}]},
        ],
        "relationships": [{"parent_table": "tests", "parent_key": "tid", "child_table": "results",
                           "child_key": "tid", "child_count_min": 5, "child_count_max": 10}],
        "cross_table_constraints": [{"parent_table": "tests", "child_table": "results",
            "child_key": "tid", "parent_column": "maximum", "child_column": "score",
            "operator": "less_or_equal"}],
    })
    report = run(spec)["report"]
    check = report["evaluation"]["cross_table_checks"][0]
    assert check["passed"] and check["failing_rows"] == 0
    assert check["skipped_rows"] > 0  # disclosed, not hidden
    assert report["summary"]["all_constraints_passed"]
