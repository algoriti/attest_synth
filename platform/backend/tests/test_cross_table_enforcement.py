"""Cross-table rules are enforced during generation, whatever the domain."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthetic_platform.pipeline import run
from synthetic_platform.spec import SyntheticDataSpec


def _spec(parent_cols, child_cols, rule, parent_rows=20, per_parent=(3, 6)):
    return SyntheticDataSpec.model_validate({
        "name": "t", "mode": "relational_rules", "purpose": "software_testing",
        "engine": "relational_rules", "seed": 7,
        "tables": [
            {"name": "parent", "rows": parent_rows, "primary_key": "pid",
             "columns": [{"name": "pid", "type": "integer", "role": "identifier"}, *parent_cols]},
            {"name": "child", "primary_key": "cid",
             "columns": [{"name": "cid", "type": "integer", "role": "identifier"},
                         {"name": "pid", "type": "integer", "role": "foreign_key"}, *child_cols]},
        ],
        "relationships": [{"parent_table": "parent", "parent_key": "pid", "child_table": "child",
                           "child_key": "pid", "child_count_min": per_parent[0],
                           "child_count_max": per_parent[1]}],
        "cross_table_constraints": [rule],
    })


def _joined(result, parent_column, child_column):
    frames = result["frames"]
    bound = frames["child"]["pid"].map(frames["parent"].set_index("pid")[parent_column])
    return frames["child"][child_column], bound


def test_scores_never_exceed_their_maximum():
    """Education: a score redrawn under its assessment's maximum."""
    spec = _spec(
        [{"name": "maximum_score", "type": "integer", "role": "rule",
          "rule": {"kind": "choice", "values": [10, 20, 50]}}],
        [{"name": "score", "type": "integer", "role": "rule",
          "rule": {"kind": "integer_range", "start": 0, "end": 100}}],
        {"parent_table": "parent", "child_table": "child", "child_key": "pid",
         "parent_column": "maximum_score", "child_column": "score", "operator": "less_or_equal"},
    )
    result = run(spec)
    score, maximum = _joined(result, "maximum_score", "score")
    assert (score <= maximum).all()
    assert (score >= 0).all()
    assert result["report"]["summary"]["all_constraints_passed"]
    repairs = result["report"]["evaluation"]["cross_table_repairs"]
    assert repairs[0]["repaired_rows"] > 0  # it had to act, and says so


def test_delivery_never_precedes_its_order():
    """Retail: a timestamp lower-bounded by its parent's timestamp."""
    spec = _spec(
        [{"name": "ordered_at", "type": "timestamp", "role": "rule",
          "rule": {"kind": "timestamp_range", "start": "2026-01-01", "end": "2026-06-30"}}],
        [{"name": "delivered_at", "type": "timestamp", "role": "rule",
          "rule": {"kind": "timestamp_range", "start": "2026-01-01", "end": "2026-06-30"}}],
        {"parent_table": "parent", "child_table": "child", "child_key": "pid",
         "parent_column": "ordered_at", "child_column": "delivered_at",
         "operator": "greater_or_equal"},
    )
    result = run(spec)
    delivered, ordered = _joined(result, "ordered_at", "delivered_at")
    assert (pd.to_datetime(delivered, utc=True) >= pd.to_datetime(ordered, utc=True)).all()
    assert result["report"]["summary"]["all_constraints_passed"]


def test_payments_stay_under_invoice_totals():
    """Finance: a decimal amount bounded by its parent amount, rounding kept inside."""
    spec = _spec(
        [{"name": "invoice_total", "type": "number", "role": "rule",
          "rule": {"kind": "number_range", "start": 50, "end": 500, "decimals": 2}}],
        [{"name": "paid", "type": "number", "role": "rule",
          "rule": {"kind": "number_range", "start": 0, "end": 1000, "decimals": 2}}],
        {"parent_table": "parent", "child_table": "child", "child_key": "pid",
         "parent_column": "invoice_total", "child_column": "paid", "operator": "less_or_equal"},
    )
    paid, total = _joined(run(spec), "invoice_total", "paid")
    assert (paid <= total + 1e-9).all()
    assert (paid.round(2) == paid).all()


def test_conflicting_rules_are_reported_not_overridden():
    """A parent cap below the child's declared range is unsatisfiable, and says so.

    The child's declared 5-14 range must not be silently replaced by values the
    person never declared just to make the cross-table check pass.
    """
    spec = _spec(
        [{"name": "cap", "type": "number", "role": "constant", "constant_value": 1}],
        [{"name": "hours", "type": "number", "role": "rule", "minimum": 0,
          "rule": {"kind": "number_range", "start": 5, "end": 14}}],
        {"parent_table": "parent", "child_table": "child", "child_key": "pid",
         "parent_column": "cap", "child_column": "hours", "operator": "less_or_equal"},
    )
    result = run(spec)
    hours, _ = _joined(result, "cap", "hours")
    assert (hours >= 5).all()
    assert not result["report"]["summary"]["all_constraints_passed"]
    repairs = result["report"]["evaluation"]["cross_table_repairs"]
    assert repairs[0]["unsatisfiable_rows"] > 0 and repairs[0]["repaired_rows"] == 0
