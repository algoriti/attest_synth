"""End-to-end demonstration on real attendance data.

Runs the same generator twice over the same source: once naively, with every column
treated as something to learn, and once through the platform, with the business rules
the profiler found marked as derived.

The naive run is the control. It exists to show the failure this platform is built to
prevent: rows whose overtime contradicts their own shift length, produced by a
generator whose per-column distributions look perfectly healthy.

Raw timestamps are turned into two numeric features first — clock-in hour and shift
length — because ARF models tabular attributes rather than datetimes. That is an
ordinary modelling choice, and it leaves the two business rules intact, since both are
computed from exactly those quantities.

Usage:
    python demo_attendance.py [path/to/Attendance.csv] [--rows N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from synthetic_platform.pipeline import run  # noqa: E402
from synthetic_platform.profile import profile_csv  # noqa: E402
from synthetic_platform.spec import (  # noqa: E402
    Constraint,
    ConstraintOperator,
    Evaluation,
    Mode,
    Origin,
    PrivacyIntent,
    Provenance,
    Purpose,
    SemanticRole,
    SyntheticDataSpec,
)

DEFAULT_CSV = "/home/administrator/Documents/Attendance.csv"
TZ_OFFSET = 3.0  # site wall clock, needed for the "late after 07:45" rule
LATE_CUTOFF = 7.75
STANDARD_DAY = 6.0
MAX_PLAUSIBLE_SHIFT = 24.0


def engineer(source: pd.DataFrame) -> pd.DataFrame:
    """Turn timestamps into the two quantities the business rules actually use."""
    time_in = pd.to_datetime(source["attendance_time_in"], format="mixed", utc=True, errors="coerce")
    time_out = pd.to_datetime(source["attendance_time_out"], format="mixed", utc=True, errors="coerce")
    local_in = time_in + pd.Timedelta(hours=TZ_OFFSET)

    frame = pd.DataFrame(
        {
            "attendance_unique_id": source["attendance_unique_id"],
            "attendance_user_id": source["attendance_user_id"],
            "clock_in_hour": (local_in.dt.hour + local_in.dt.minute / 60.0).round(4),
            "shift_hours": ((time_out - time_in).dt.total_seconds() / 3600.0).round(4),
            "late_status": source["late_status"].astype(bool),
            "extra_hours": source["extra_hours"].astype(int),
        }
    )

    # Unclosed sessions are 11% of this export and reach 12,510 hours. Learning from
    # them would teach the generator that a shift can last most of a year.
    before = len(frame)
    frame = frame[frame.shift_hours.notna() & frame.shift_hours.between(0, MAX_PLAUSIBLE_SHIFT)]
    frame = frame.reset_index(drop=True)
    print(f"  dropped {before - len(frame):,} rows with missing or implausible shift length")
    return frame


def rule_violations(frame: pd.DataFrame) -> dict:
    """Count rows contradicting the two rules the profiler found in the source.

    The expected value applies the same 0..14 clip the specification declares, so this
    check measures the rule as stated rather than an idealised version of it.
    """
    expected_extra = np.clip(np.round(frame["shift_hours"] - STANDARD_DAY), 0, 14)
    extra_bad = int((frame["extra_hours"] != expected_extra).sum())

    expected_late = frame["clock_in_hour"] > LATE_CUTOFF
    late_bad = int((frame["late_status"].astype(bool) != expected_late).sum())

    negative = int((frame["shift_hours"] < 0).sum())
    total = len(frame)

    # The source uses extra_hours == 0 as a catch-all for short, broken and unclosed
    # sessions, so the rule genuinely does not hold there. Excluding that bucket shows
    # how well the rule describes the rows it was ever meant to cover.
    nonzero = frame["extra_hours"] > 0
    extra_bad_nonzero = int((frame.loc[nonzero, "extra_hours"] != expected_extra[nonzero]).sum())

    return {
        "rows": total,
        "extra_hours_contradicts_shift_length": extra_bad,
        "extra_hours_contradicts_excluding_zero_bucket": extra_bad_nonzero,
        "nonzero_rows": int(nonzero.sum()),
        "late_status_contradicts_clock_in": late_bad,
        "negative_shift_length": negative,
        "worst_pct": round(100.0 * max(extra_bad, late_bad) / total, 2) if total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--rows", type=int, default=2000)
    args = parser.parse_args()

    raw = pd.read_csv(args.csv, low_memory=False)
    print(f"Source: {args.csv}")
    print(f"  {len(raw):,} rows x {len(raw.columns)} columns")

    # --- 1. profile the raw export ---------------------------------------------
    _, raw_report = profile_csv(raw, "attendance_raw", tz_offset_hours=TZ_OFFSET)
    print("\nPROFILER on the raw export")
    print(f"  roles proposed: {raw_report['role_summary']}")
    applied = [n for n in raw_report["notes"] if n.get("applied")]
    print("  business rules found:")
    for note in applied:
        print(f"    {note['agreement']:.2%}  {note['message'].split(' (')[0]}")
    for note in raw_report["quality"][:1]:
        print(f"  quality: {note['message'][:120]}")

    # --- 2. engineer features and re-profile ------------------------------------
    print("\nFEATURE ENGINEERING")
    source = engineer(raw)
    table, report = profile_csv(source, "attendance", tz_offset_hours=TZ_OFFSET)
    print(f"  {len(source):,} usable rows, roles: {report['role_summary']}")

    # The profiler proposes; the specification confirms. Both rules are pinned to the
    # cutoffs found in the source rather than left to a re-derivation at generate time.
    late = table.column("late_status")
    assert late is not None
    late.role = SemanticRole.DERIVED
    late.formula = __import__("synthetic_platform.spec", fromlist=["Expr"]).Expr.model_validate(
        {"op": "gt", "args": [{"col": "clock_in_hour"}, {"const": LATE_CUTOFF}]}
    )
    late.description = f"late when clock-in is after {LATE_CUTOFF:g}h local"
    late.provenance = Provenance(
        origin=Origin.PROFILED, detail="97.8% match in source", confirmed=True
    )

    extra = table.column("extra_hours")
    assert extra is not None
    extra.role = SemanticRole.DERIVED
    extra.formula = __import__("synthetic_platform.spec", fromlist=["Expr"]).Expr.model_validate(
        {
            "op": "clip",
            "args": [
                {"op": "round", "args": [{"op": "sub", "args": [{"col": "shift_hours"}, {"const": STANDARD_DAY}]}]},
                {"const": 0},
                {"const": 14},
            ],
        }
    )
    extra.description = f"hours worked beyond a {STANDARD_DAY:g}-hour standard day"
    extra.provenance = Provenance(
        origin=Origin.PROFILED, detail="99.2% match in source", confirmed=True
    )

    table.constraints = [
        Constraint(
            operator=ConstraintOperator.UNIQUE,
            columns=["attendance_unique_id"],
            description="Every record has its own identifier",
            provenance=Provenance(origin=Origin.USER, confirmed=True),
        ),
        Constraint(
            operator=ConstraintOperator.RANGE,
            columns=["extra_hours"],
            minimum=0,
            maximum=14,
            description="Overtime stays within the observed range",
            provenance=Provenance(origin=Origin.PROFILED, confirmed=True),
        ),
        Constraint(
            operator=ConstraintOperator.RANGE,
            columns=["shift_hours"],
            minimum=0,
            maximum=MAX_PLAUSIBLE_SHIFT,
            description="A shift fits inside a day",
            provenance=Provenance(origin=Origin.PROFILED, confirmed=True),
        ),
    ]

    spec = SyntheticDataSpec(
        name="attendance_demo",
        mode=Mode.LEARNED_TABLE,
        purpose=Purpose.ML_DEVELOPMENT,
        description="Synthetic attendance behaviour learned from an approved export.",
        engine="arf",
        seed=2026,
        tables=[table],
        privacy=PrivacyIntent(
            protected_entity="employee",
            notes="Learned from real records. No privacy mechanism applied.",
        ),
        # The utility target is deliberately a *learned* column. Predicting a derived
        # column such as late_status would score near-perfectly by construction and
        # would measure the formula rather than the synthesis.
        evaluation=Evaluation(
            checks=["schema", "constraints", "fidelity", "predictive_utility"],
            target="shift_hours",
            task="regression",
        ),
    )

    print("\nGenerating through the platform (derived columns computed after generation)...")
    result = run(spec, sources={"attendance": source}, rows=args.rows)
    frame = result["frames"]["attendance"]
    platform_report = result["report"]

    print("Generating the naive control (every column learned)...")
    naive_table = table.model_copy(deep=True)
    for column in naive_table.columns:
        if column.role == SemanticRole.DERIVED:
            column.role = SemanticRole.LEARNED
            column.formula = None
    naive_table.constraints = []
    naive_spec = spec.model_copy(deep=True)
    naive_spec.name = "attendance_naive_control"
    naive_spec.tables = [naive_table]
    naive_spec.evaluation = Evaluation(checks=["schema"])
    naive_frame = run(naive_spec, sources={"attendance": source}, rows=args.rows)["frames"]["attendance"]

    # --- 3. compare --------------------------------------------------------------
    naive = rule_violations(naive_frame)
    ours = rule_violations(frame)
    real = rule_violations(source)

    print()
    print("=" * 78)
    print("INTERNAL CONSISTENCY — rows contradicting the source's own business rules")
    print("=" * 78)
    print(f"{'check':<44}{'real':>10}{'naive':>11}{'platform':>12}")
    print("-" * 78)
    for key in (
        "extra_hours_contradicts_shift_length",
        "extra_hours_contradicts_excluding_zero_bucket",
        "late_status_contradicts_clock_in",
        "negative_shift_length",
    ):
        print(f"{key:<44}{real[key]:>10,}{naive[key]:>11,}{ours[key]:>12,}")
    print("-" * 78)
    print(f"{'worst-case contradiction rate':<44}{real['worst_pct']:>9.2f}%{naive['worst_pct']:>10.2f}%{ours['worst_pct']:>11.2f}%")
    print(f"{'rows':<44}{real['rows']:>10,}{naive['rows']:>11,}{ours['rows']:>12,}")
    print()
    print(
        "  The real column is itself inconsistent because the source uses extra_hours == 0\n"
        "  as a catch-all for short and unclosed sessions; the second row excludes that\n"
        "  bucket. The platform run reproduces the rule as the specification states it."
    )
    print()

    print("DECLARED CONSTRAINTS (platform run)")
    for check in platform_report["tables"][0]["constraints"]:
        print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {check['operator']:<14} {check.get('description','')}")

    print("\nIDENTIFIERS")
    overlap = len(set(frame["attendance_unique_id"]) & set(source["attendance_unique_id"]))
    print(f"  synthetic identifiers also present in the source: {overlap}")
    print(f"  unique in output: {frame['attendance_unique_id'].is_unique}")

    evaluation = platform_report["evaluation"]
    fid = evaluation.get("fidelity", {})
    if fid.get("mean_numeric_ks") is not None:
        print("\nFIDELITY")
        print(f"  mean numeric KS        {fid['mean_numeric_ks']:.4f}   (0 = identical distributions)")
        if fid.get("mean_categorical_tv") is not None:
            print(f"  mean categorical TV    {fid['mean_categorical_tv']:.4f}")
        if fid.get("numeric_correlation_mae") is not None:
            print(f"  correlation error      {fid['numeric_correlation_mae']:.4f}")
        print(f"  exact row matches      {fid['exact_row_match_fraction']:.4%}  (diagnostic, not a privacy score)")

    util = evaluation.get("predictive_utility", {})
    if util and "error" not in util:
        print(f"\nPREDICTIVE UTILITY — target '{util['target']}' ({util['metric']}, {util['better']} is better)")
        for label, key in [
            ("trained on real", "trained_on_real"),
            ("trained on synthetic", "trained_on_synthetic"),
            ("independent baseline", "trained_on_independent_baseline"),
        ]:
            block = util.get(key, {})
            value = block.get(util["metric"])
            print(f"  {label:<24}{value:.4f}" if value is not None else f"  {label:<24}{block}")

    summary = platform_report["summary"]
    print("\nREPORT SUMMARY")
    print(f"  rows requested/generated  {args.rows} / {summary['total_rows']}")
    print(f"  all constraints passed    {summary['all_constraints_passed']}")
    print(f"  open assumptions          {summary['open_assumptions']}")
    print(f"  elapsed                   {summary['elapsed_seconds']}s")

    out_dir = Path(__file__).resolve().parent / "demo_output"
    out_dir.mkdir(exist_ok=True)
    frame.to_csv(out_dir / "attendance_synthetic.csv", index=False)
    naive_frame.to_csv(out_dir / "attendance_naive_control.csv", index=False)
    (out_dir / "evidence_report.json").write_text(json.dumps(platform_report, indent=2, default=str))
    (out_dir / "specification.json").write_text(spec.model_dump_json(indent=2))
    print(f"\nArtefacts written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
