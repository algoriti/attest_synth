"""Profile an uploaded CSV into a proposed specification.

Everything this module returns is a *proposal*. Nothing is applied until a person
confirms it, which is why each suggested column carries `Origin.PROFILED` and each
guessed rule carries `Origin.ASSISTANT_PROPOSED`.

The detectors here exist because profiling the project's real attendance export turned
up three traps that a dtype-based profiler walks straight into:

  - `attendance_created_by` was 100% null — nothing to model, but a naive profiler
    happily declares a float column and emits NaNs forever.
  - `attendance_is_active` was a single value across all 28,549 rows.
  - `entry_or_exit_status` was exactly `attendance_time_out is null`, 156 times out of
    156, and `extra_hours` was `round(shift_hours - 6)` to 99.2%.

The last two are business rules. Left as `learned`, a generator reproduces their
marginal frequency while contradicting the columns they are computed from.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import numpy as np
import pandas as pd

from .spec import (
    Column,
    ColumnType,
    Expr,
    Origin,
    Provenance,
    Rule,
    RuleKind,
    SemanticRole,
    SemanticRole as Role,
    Source,
    SourceKind,
    Table,
)

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
ID_NAME_PATTERN = re.compile(r"(^|_)(id|key|uuid|guid|code|number|no)$", re.IGNORECASE)

# How closely a candidate formula must match before it is proposed as derived.
DERIVED_MATCH_THRESHOLD = 0.95
# Below this, a near-match is still surfaced as a data-quality note.
DERIVED_HINT_THRESHOLD = 0.80


def profile_csv(
    frame: pd.DataFrame,
    table_name: str = "uploaded",
    tz_offset_hours: float = 0.0,
) -> tuple[Table, dict]:
    """Return a proposed table plus a profiling report."""
    columns: list[Column] = []
    notes: list[dict] = []

    parsed = _parse_temporal(frame)

    for name in frame.columns:
        column, column_notes = _profile_column(name, frame[name], parsed.get(name))
        columns.append(column)
        notes.extend(column_notes)

    table = Table(
        name=table_name,
        rows=len(frame),
        columns=columns,
        source=Source(
            kind=SourceKind.UPLOADED_CSV,
            row_count=len(frame),
            sha256=_frame_hash(frame),
        ),
    )

    derived_findings = detect_derived(frame, table, parsed, tz_offset_hours)
    # `detect_derived` returns candidates sorted by agreement, and a column often has
    # several. Only the strongest is applied; the rest stay visible as notes so a
    # reviewer can see what else the column nearly matched.
    claimed: set[str] = set()
    for finding in derived_findings:
        is_best = finding["column"] not in claimed
        if finding["agreement"] >= DERIVED_MATCH_THRESHOLD and is_best:
            column = table.column(finding["column"])
            if column is not None:
                claimed.add(finding["column"])
                column.role = Role.DERIVED
                column.formula = Expr.model_validate(finding["formula"])
                column.description = finding["explanation"]
                column.provenance = Provenance(
                    origin=Origin.ASSISTANT_PROPOSED,
                    detail=(
                        f"{finding['explanation']} Matches {finding['agreement']:.1%} of "
                        "source rows. Confirm before generating."
                    ),
                )
        applied = finding["agreement"] >= DERIVED_MATCH_THRESHOLD and is_best
        if applied:
            tail = "Proposed as a derived column so it is computed, not generated."
        elif finding["agreement"] >= DERIVED_MATCH_THRESHOLD:
            tail = "An alternative match for this column; a stronger formula was chosen."
        else:
            tail = "Close but not exact; review before relying on it."
        notes.append(
            {
                "column": finding["column"],
                "kind": "derived_candidate",
                "severity": "high" if applied else "info",
                "applied": applied,
                "agreement": round(finding["agreement"], 4),
                "message": f"{finding['explanation']} ({finding['agreement']:.1%} of rows). {tail}",
            }
        )

    quality = _quality_notes(frame, parsed)
    report = {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "sha256": table.source.sha256,
        "notes": notes,
        "quality": quality,
        "role_summary": _role_summary(table),
    }
    return table, report


def _frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    ).hexdigest()


def _parse_temporal(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Find columns that are really timestamps hiding in object dtype."""
    parsed: dict[str, pd.Series] = {}
    for name in frame.columns:
        series = frame[name]
        if pd.api.types.is_datetime64_any_dtype(series):
            parsed[name] = series
            continue
        if series.dtype != object:
            continue
        sample = series.dropna().head(200)
        if sample.empty:
            continue
        if not sample.astype(str).str.contains(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}").any():
            continue
        try:
            converted = pd.to_datetime(series, format="mixed", utc=True, errors="coerce")
        except Exception:
            continue
        if converted.notna().mean() > 0.9:
            parsed[name] = converted
    return parsed


def _profile_column(
    name: str, series: pd.Series, temporal: pd.Series | None
) -> tuple[Column, list[dict]]:
    notes: list[dict] = []
    non_null = series.dropna()
    null_fraction = float(series.isna().mean())
    distinct = int(series.nunique(dropna=True))

    # 1. Entirely empty.
    if len(non_null) == 0:
        notes.append(
            {
                "column": name,
                "kind": "empty_column",
                "severity": "high",
                "message": "Every value is null. Nothing can be learned; proposed as an empty column.",
            }
        )
        return (
            Column(
                name=name,
                type=ColumnType.STRING,
                role=Role.EMPTY,
                nullable=True,
                null_fraction=1.0,
                description="No values observed in the source.",
                provenance=Provenance(origin=Origin.PROFILED, detail="100% null in source"),
            ),
            notes,
        )

    # 2. Single value throughout.
    if distinct == 1:
        value = non_null.iloc[0]
        notes.append(
            {
                "column": name,
                "kind": "constant_column",
                "severity": "info",
                "message": f"Single value across all rows ({value!r}). Proposed as a constant.",
            }
        )
        return (
            Column(
                name=name,
                type=_infer_type(series, temporal),
                role=Role.CONSTANT,
                constant_value=_native(value),
                description="Constant in the source.",
                provenance=Provenance(origin=Origin.PROFILED, detail="single distinct value"),
            ),
            notes,
        )

    column_type = _infer_type(series, temporal)

    # 3. Identifier: unique, and either UUID-shaped or named like a key.
    looks_unique = distinct == len(non_null)
    is_uuid = column_type == ColumnType.UUID
    named_like_id = bool(ID_NAME_PATTERN.search(name))
    if looks_unique and (is_uuid or named_like_id):
        notes.append(
            {
                "column": name,
                "kind": "identifier",
                "severity": "high",
                "message": "Unique per row and named or shaped like a key. Will be regenerated, "
                "never copied from the source.",
            }
        )
        return (
            Column(
                name=name,
                type=column_type,
                role=Role.IDENTIFIER,
                sensitive=True,
                description="Identifier; regenerated for synthetic output.",
                provenance=Provenance(origin=Origin.PROFILED, detail="unique key-shaped column"),
            ),
            notes,
        )

    column = Column(
        name=name,
        type=column_type,
        role=Role.LEARNED,
        nullable=null_fraction > 0,
        null_fraction=null_fraction,
        provenance=Provenance(
            origin=Origin.PROFILED, detail=f"{distinct} distinct values, {null_fraction:.1%} null"
        ),
    )

    if column_type in (ColumnType.INTEGER, ColumnType.NUMBER):
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if len(numeric):
            column.minimum = float(numeric.min())
            column.maximum = float(numeric.max())
    elif column_type == ColumnType.CATEGORY:
        column.allowed_values = [_native(v) for v in sorted(non_null.unique(), key=str)]

    if null_fraction > 0.3:
        notes.append(
            {
                "column": name,
                "kind": "high_missingness",
                "severity": "info",
                "message": f"{null_fraction:.1%} of values are missing.",
            }
        )
    return column, notes


def _infer_type(series: pd.Series, temporal: pd.Series | None) -> ColumnType:
    if temporal is not None:
        as_dt = temporal.dropna()
        if len(as_dt) and (as_dt.dt.floor("D") == as_dt).all():
            return ColumnType.DATE
        return ColumnType.TIMESTAMP
    if pd.api.types.is_bool_dtype(series):
        return ColumnType.BOOLEAN
    if pd.api.types.is_integer_dtype(series):
        return ColumnType.INTEGER
    if pd.api.types.is_float_dtype(series):
        return ColumnType.NUMBER
    non_null = series.dropna().astype(str)
    if len(non_null) and non_null.head(200).str.match(UUID_PATTERN).all():
        return ColumnType.UUID
    if series.nunique(dropna=True) <= max(20, int(0.05 * len(series))):
        return ColumnType.CATEGORY
    return ColumnType.STRING


def _native(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


# --- derived-column detection ----------------------------------------------------


def detect_derived(
    frame: pd.DataFrame,
    table: Table,
    parsed: dict[str, pd.Series],
    tz_offset_hours: float = 0.0,
) -> list[dict]:
    """Search for columns that are deterministic functions of other columns."""
    findings: list[dict] = []
    findings.extend(_detect_null_flags(frame, table))
    findings.extend(_detect_duration_offsets(frame, table, parsed))
    findings.extend(_detect_threshold_flags(frame, table, parsed, tz_offset_hours))
    findings.extend(_detect_products(frame, table))
    return sorted(findings, key=lambda f: -f["agreement"])


def _boolean_columns(frame: pd.DataFrame, table: Table) -> list[str]:
    names = []
    for column in table.columns:
        series = frame[column.name]
        if pd.api.types.is_bool_dtype(series) or set(series.dropna().unique()) <= {0, 1, True, False}:
            if series.nunique(dropna=True) == 2:
                names.append(column.name)
    return names


def _detect_null_flags(frame: pd.DataFrame, table: Table) -> list[dict]:
    """A boolean that is exactly 'some other column is null'."""
    findings = []
    nullable = [c for c in frame.columns if frame[c].isna().any()]
    for flag in _boolean_columns(frame, table):
        flag_values = frame[flag].astype(bool)
        for target in nullable:
            if target == flag:
                continue
            agreement = float((flag_values == frame[target].isna()).mean())
            if agreement >= DERIVED_HINT_THRESHOLD:
                findings.append(
                    {
                        "column": flag,
                        "agreement": agreement,
                        "explanation": f"'{flag}' is true exactly when '{target}' is missing",
                        "formula": {"op": "is_null", "args": [{"col": target}]},
                    }
                )
    return findings


def _detect_duration_offsets(
    frame: pd.DataFrame, table: Table, parsed: dict[str, pd.Series]
) -> list[dict]:
    """An integer column that is round(hours_between(a, b) - k)."""
    findings = []
    stamps = [n for n in parsed if n in frame.columns]
    numeric_cols = [
        c.name
        for c in table.columns
        if c.type in (ColumnType.INTEGER, ColumnType.NUMBER) and c.name in frame.columns
    ]

    for start in stamps:
        for end in stamps:
            if start == end:
                continue
            duration = (parsed[end] - parsed[start]).dt.total_seconds() / 3600.0
            # Restrict to plausible same-shift rows; wild values are data-quality noise
            # that would otherwise drown a real relationship.
            usable = duration.notna() & (duration >= 0) & (duration < 24)
            if usable.sum() < max(50, 0.2 * len(frame)):
                continue

            for target in numeric_cols:
                values = pd.to_numeric(frame[target], errors="coerce")
                positive = usable & (values > 0)
                if positive.sum() < 50:
                    continue
                offsets = (duration[positive] - values[positive]).median()
                if not np.isfinite(offsets):
                    continue
                offset = float(np.round(offsets * 2) / 2)  # nearest half hour
                predicted = np.round(duration[positive] - offset)
                agreement = float((predicted == values[positive]).mean())
                if agreement >= DERIVED_HINT_THRESHOLD:
                    findings.append(
                        {
                            "column": target,
                            "agreement": agreement,
                            "explanation": (
                                f"'{target}' equals the hours between '{start}' and "
                                f"'{end}' minus {offset:g}, rounded"
                            ),
                            "formula": {
                                "op": "clip",
                                "args": [
                                    {
                                        "op": "round",
                                        "args": [
                                            {
                                                "op": "sub",
                                                "args": [
                                                    {
                                                        "op": "duration_hours",
                                                        "args": [{"col": start}, {"col": end}],
                                                    },
                                                    {"const": offset},
                                                ],
                                            }
                                        ],
                                    },
                                    {"const": 0},
                                    {"const": float(values.max())},
                                ],
                            },
                        }
                    )
    return findings


def _detect_threshold_flags(
    frame: pd.DataFrame,
    table: Table,
    parsed: dict[str, pd.Series],
    tz_offset_hours: float,
) -> list[dict]:
    """A boolean that is 'this timestamp's clock time is past some cutoff'."""
    findings = []
    for flag in _boolean_columns(frame, table):
        flag_values = frame[flag].astype(bool)
        for name, stamps in parsed.items():
            if name == flag:
                continue
            local = stamps + pd.Timedelta(hours=tz_offset_hours)
            clock = local.dt.hour + local.dt.minute / 60.0
            if clock.isna().all():
                continue
            best_agreement, best_cut = 0.0, None
            for cut in np.arange(0, 24, 0.25):
                agreement = float(((clock > cut) == flag_values).mean())
                if agreement > best_agreement:
                    best_agreement, best_cut = agreement, float(cut)
            if best_agreement >= DERIVED_HINT_THRESHOLD and best_cut is not None:
                hours, minutes = int(best_cut), int(round((best_cut % 1) * 60))
                findings.append(
                    {
                        "column": flag,
                        "agreement": best_agreement,
                        "explanation": (
                            f"'{flag}' is true when '{name}' is later than "
                            f"{hours:02d}:{minutes:02d} local time"
                        ),
                        "formula": {
                            "op": "gt",
                            "args": [
                                {
                                    "op": "time_of_day",
                                    "args": [{"col": name}],
                                    "tz_offset_hours": tz_offset_hours,
                                },
                                {"const": best_cut},
                            ],
                        },
                    }
                )
    return findings


def _detect_products(frame: pd.DataFrame, table: Table) -> list[dict]:
    """c == a * b, the classic line-total relationship."""
    findings = []
    numeric = [
        c.name
        for c in table.columns
        if c.type in (ColumnType.INTEGER, ColumnType.NUMBER) and c.name in frame.columns
    ]
    for target in numeric:
        target_values = pd.to_numeric(frame[target], errors="coerce")
        for a in numeric:
            for b in numeric:
                if len({a, b, target}) != 3:
                    continue
                product = pd.to_numeric(frame[a], errors="coerce") * pd.to_numeric(
                    frame[b], errors="coerce"
                )
                usable = product.notna() & target_values.notna()
                if usable.sum() < 50:
                    continue
                agreement = float(
                    (np.abs(product[usable] - target_values[usable]) < 1e-6).mean()
                )
                if agreement >= DERIVED_MATCH_THRESHOLD:
                    findings.append(
                        {
                            "column": target,
                            "agreement": agreement,
                            "explanation": f"'{target}' equals '{a}' multiplied by '{b}'",
                            "formula": {"op": "mul", "args": [{"col": a}, {"col": b}]},
                        }
                    )
                    break
    return findings


def _quality_notes(frame: pd.DataFrame, parsed: dict[str, pd.Series]) -> list[dict]:
    """Data-quality problems that would poison a learned model if left alone."""
    notes: list[dict] = []
    stamps = list(parsed)

    for start in stamps:
        for end in stamps:
            if start == end:
                continue
            duration = (parsed[end] - parsed[start]).dt.total_seconds() / 3600.0
            valid = duration.dropna()
            if len(valid) < 50 or (valid < 0).mean() > 0.5:
                continue
            extreme = float((valid > 24).mean())
            if extreme > 0.01:
                notes.append(
                    {
                        "kind": "implausible_duration",
                        "severity": "high",
                        "message": (
                            f"{extreme:.1%} of rows span more than 24 hours between "
                            f"'{start}' and '{end}' (longest {valid.max():,.0f}h). These "
                            "are usually unclosed sessions and will distort anything "
                            "learned from the column."
                        ),
                    }
                )
    duplicates = int(frame.duplicated().sum())
    if duplicates:
        notes.append(
            {
                "kind": "duplicate_rows",
                "severity": "info",
                "message": f"{duplicates} exactly duplicated rows in the source.",
            }
        )
    return notes


def _role_summary(table: Table) -> dict[str, int]:
    summary: dict[str, int] = {}
    for column in table.columns:
        summary[column.role.value] = summary.get(column.role.value, 0) + 1
    return summary
