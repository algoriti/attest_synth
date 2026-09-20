"""Evaluate derived-column expressions over a generated table.

Derived columns are computed here, after generation, from the columns a generator was
actually allowed to model. That ordering is the point. Attendance data profiled for
this project carries `extra_hours = round(shift_hours - 6)` at 99.2% agreement and
`late_status = clocked in after 07:45 local` at 97.6%; handing those to a learned
generator as ordinary columns produces rows whose overtime contradicts their own
timestamps while every marginal-distribution metric still looks healthy.

Expressions are a small typed tree rather than Python or SQL, because specifications
arrive over HTTP and from an LLM. There is no eval() here and no way to reach one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .spec import Column, Expr, SemanticRole, Table


class DerivationError(ValueError):
    """Raised when an expression cannot be evaluated against the frame it is given."""


def _as_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    return pd.to_datetime(series, format="mixed", utc=True, errors="coerce")


def _numeric(value: object) -> object:
    """Coerce a bool-typed series to numbers so arithmetic behaves predictably."""
    if isinstance(value, pd.Series) and value.dtype == bool:
        return value.astype(float)
    return value


def evaluate(expr: Expr, frame: pd.DataFrame) -> pd.Series | object:
    """Evaluate one expression node against `frame`."""
    if expr.col is not None:
        if expr.col not in frame.columns:
            raise DerivationError(f"formula references unknown column '{expr.col}'")
        return frame[expr.col]
    if expr.const is not None:
        return expr.const

    args = [evaluate(a, frame) for a in expr.args]
    op = expr.op

    # --- arithmetic ---
    if op == "add":
        return sum(_numeric(a) for a in args)
    if op == "sub":
        return _numeric(args[0]) - _numeric(args[1])
    if op == "mul":
        result = _numeric(args[0])
        for a in args[1:]:
            result = result * _numeric(a)
        return result
    if op == "div":
        denominator = _numeric(args[1])
        # A zero denominator is a specification error, not something to paper over with
        # a silent NaN that would survive into the delivered dataset.
        if isinstance(denominator, pd.Series):
            if (denominator == 0).any():
                raise DerivationError("division by zero in derived column")
        elif denominator == 0:
            raise DerivationError("division by zero in derived column")
        return _numeric(args[0]) / denominator
    if op == "round":
        return np.round(_numeric(args[0]))
    if op == "floor":
        return np.floor(_numeric(args[0]))
    if op == "ceil":
        return np.ceil(_numeric(args[0]))
    if op == "abs":
        return np.abs(_numeric(args[0]))
    if op == "clip":
        return np.clip(_numeric(args[0]), args[1], args[2])
    if op == "min":
        return np.minimum.reduce([np.asarray(_numeric(a)) for a in args])
    if op == "max":
        return np.maximum.reduce([np.asarray(_numeric(a)) for a in args])

    # --- comparison ---
    if op == "gt":
        return _numeric(args[0]) > _numeric(args[1])
    if op == "ge":
        return _numeric(args[0]) >= _numeric(args[1])
    if op == "lt":
        return _numeric(args[0]) < _numeric(args[1])
    if op == "le":
        return _numeric(args[0]) <= _numeric(args[1])
    if op == "eq":
        return args[0] == args[1]
    if op == "ne":
        return args[0] != args[1]

    # --- logic ---
    if op == "and":
        result = args[0]
        for a in args[1:]:
            result = result & a
        return result
    if op == "or":
        result = args[0]
        for a in args[1:]:
            result = result | a
        return result
    if op == "not":
        return ~args[0].astype(bool) if isinstance(args[0], pd.Series) else (not args[0])
    if op == "if_else":
        condition, when_true, when_false = args
        return pd.Series(np.where(condition, when_true, when_false), index=frame.index)

    # --- nulls ---
    if op == "is_null":
        return args[0].isna() if isinstance(args[0], pd.Series) else args[0] is None
    if op == "not_null":
        return args[0].notna() if isinstance(args[0], pd.Series) else args[0] is not None
    if op == "coalesce":
        result = args[0]
        for a in args[1:]:
            result = result.fillna(a) if isinstance(result, pd.Series) else result
        return result

    # --- temporal ---
    if op == "duration_hours":
        start, end = _as_datetime(args[0]), _as_datetime(args[1])
        return (end - start).dt.total_seconds() / 3600.0
    if op == "time_of_day":
        moment = _as_datetime(args[0])
        shifted = moment + pd.Timedelta(hours=expr.tz_offset_hours)
        return shifted.dt.hour + shifted.dt.minute / 60.0 + shifted.dt.second / 3600.0
    if op == "date_of":
        return (_as_datetime(args[0]) + pd.Timedelta(hours=expr.tz_offset_hours)).dt.date
    if op == "day_of_week":
        return (_as_datetime(args[0]) + pd.Timedelta(hours=expr.tz_offset_hours)).dt.dayofweek
    if op == "add_days":
        return _as_datetime(args[0]) + pd.to_timedelta(_numeric(args[1]), unit="D")
    if op == "add_hours":
        return _as_datetime(args[0]) + pd.to_timedelta(_numeric(args[1]), unit="h")

    raise DerivationError(f"operator '{op}' is not implemented")


def derivation_order(table: Table) -> list[Column]:
    """Order derived columns so each one runs after whatever it depends on.

    Raises on a dependency cycle rather than producing a partially-filled table.
    """
    derived = [c for c in table.columns if c.role == SemanticRole.DERIVED]
    by_name = {c.name: c for c in derived}
    ordered: list[Column] = []
    resolved: set[str] = {
        c.name for c in table.columns if c.role != SemanticRole.DERIVED
    }
    remaining = list(derived)

    while remaining:
        progressed = False
        for column in list(remaining):
            assert column.formula is not None
            needs = column.formula.referenced_columns()
            if needs <= resolved:
                ordered.append(column)
                resolved.add(column.name)
                remaining.remove(column)
                progressed = True
        if not progressed:
            names = ", ".join(sorted(c.name for c in remaining))
            raise DerivationError(
                f"derived columns have a circular or unsatisfiable dependency: {names}"
            )
    # keep a stable, inspectable order for the report
    _ = by_name
    return ordered


def apply_derived(frame: pd.DataFrame, table: Table) -> tuple[pd.DataFrame, list[dict]]:
    """Compute every derived column, returning the frame and a per-column trace.

    The trace goes into the evidence report so a reader can see that these values were
    computed from a stated formula rather than sampled by the generator.
    """
    result = frame.copy()
    trace: list[dict] = []

    for column in derivation_order(table):
        assert column.formula is not None
        values = evaluate(column.formula, result)
        if not isinstance(values, pd.Series):
            values = pd.Series([values] * len(result), index=result.index)

        values = _cast_to_declared_type(values, column)
        result[column.name] = values
        trace.append(
            {
                "column": column.name,
                "depends_on": sorted(column.formula.referenced_columns()),
                "computed_rows": int(len(values)),
                "note": "computed from the specification formula, not generated",
            }
        )
    return result, trace


def _missing_value_error(column: Column, count: int, total: int) -> DerivationError:
    """Explain an uncomputable formula in terms of the input that caused it.

    "Cannot convert non-finite values to integer" tells the reader nothing about
    which column broke or why, so the message names the column, the scale of the
    problem and the usual cause: an input that is null for those rows.
    """
    inputs = ", ".join(sorted(column.formula.referenced_columns())) if column.formula else "?"
    return DerivationError(
        f"the formula for '{column.name}' could not be computed for {count:,} of "
        f"{total:,} rows, but the column is not nullable. This usually means one of its "
        f"inputs ({inputs}) is null for those rows. Either mark '{column.name}' nullable, "
        f"or wrap the formula so it produces a value there — for example with "
        f"'coalesce' or 'if_else'."
    )


def _cast_to_declared_type(values: pd.Series, column: Column) -> pd.Series:
    """Coerce a computed column to its declared type.

    A formula that cannot be evaluated for some rows is not silently filled in. If the
    column is nullable the gap is preserved as a real missing value; if it is not, that
    is a specification error and the caller is told which input caused it.
    """
    from .spec import ColumnType

    if column.type in (ColumnType.INTEGER, ColumnType.NUMBER):
        numeric = pd.to_numeric(values, errors="coerce")

        # Infinity is never a usable result and would otherwise ride out to the CSV.
        as_float = numeric.to_numpy(dtype="float64", na_value=np.nan)
        if np.isinf(as_float).any():
            raise DerivationError(
                f"the formula for '{column.name}' produced infinite values; check for a "
                "division by a near-zero quantity"
            )

        missing = numeric.isna()
        if missing.any() and not column.nullable:
            raise _missing_value_error(column, int(missing.sum()), len(numeric))

        if ((column.minimum is not None and (numeric < column.minimum).any()) or
                (column.maximum is not None and (numeric > column.maximum).any())):
            raise DerivationError(
                f"Formula for '{column.name}' exceeds its declared bounds. "
                "Correct the formula or explicitly use clip; no silent repair was applied."
            )

        if column.type == ColumnType.NUMBER:
            return numeric.astype("Float64") if missing.any() else numeric.astype(float)

        rounded = np.round(numeric)
        if ((numeric - rounded).abs() > 1e-9).any():
            raise DerivationError(f"Formula for '{column.name}' is not integral; use round explicitly.")
        # int64 cannot hold a missing value, so a nullable column uses pandas' Int64.
        return rounded.astype("Int64") if missing.any() else rounded.astype("int64")

    if column.type == ColumnType.BOOLEAN:
        missing = values.isna()
        if missing.any():
            # NaN is truthy, so a plain astype(bool) would turn every uncomputable row
            # into a confident True.
            if not column.nullable:
                raise _missing_value_error(column, int(missing.sum()), len(values))
            return values.astype("boolean")
        return values.astype(bool)

    return values
