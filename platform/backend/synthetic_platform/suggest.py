"""Deterministic rewrites for columns an engine cannot model.

When the validator rejects a column because the chosen engine does not support its
type, the fix is usually mechanical. A tree-based density estimator cannot model a raw
timestamp — arfpy either fails immediately on a real datetime or, when the column
arrives from CSV as a string, treats tens of thousands of distinct values as categories
and grinds. What it *can* model perfectly well are the quantities a timestamp is made
of: the hour of day, the day of week, an elapsed duration.

So the rewrite extracts those, lets the engine learn them, and rebuilds the timestamp
afterwards as a derived column.

The mechanism here is a lookup, not a judgement: the column's declared type and the
engine's declared capabilities fully determine whether a rewrite applies. The *content*
is a judgement — nothing in anyone's data says hour-of-day and day-of-week are the
right features to keep. That is why every column this module produces carries
`Origin.ASSISTANT_PROPOSED` and `confirmed=False`, so it appears in the report's open
assumptions until a person accepts it. A hardcoded default and a language model's guess
are the same kind of claim from the reader's point of view, and get the same label.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .spec import (
    Column,
    ColumnType,
    Expr,
    Origin,
    Provenance,
    SemanticRole,
    Table,
)

TEMPORAL_TYPES = {ColumnType.TIMESTAMP, ColumnType.DATE}


@dataclass
class Suggestion:
    """One proposed change to a specification, in a form the UI can show and apply."""

    column: str
    kind: str
    title: str
    rationale: str
    adds: list[Column] = field(default_factory=list)
    replaces_role: SemanticRole | None = None
    replaces_formula: Expr | None = None

    def as_dict(self) -> dict:
        return {
            "column": self.column,
            "kind": self.kind,
            "title": self.title,
            "rationale": self.rationale,
            "adds": [c.model_dump(mode="json") for c in self.adds],
            "replaces_role": self.replaces_role.value if self.replaces_role else None,
            "confirmed": False,
            "origin": Origin.ASSISTANT_PROPOSED.value,
        }


def _proposed(detail: str) -> Provenance:
    return Provenance(origin=Origin.ASSISTANT_PROPOSED, detail=detail, confirmed=False)


def suggest_for_table(
    table: Table, capabilities: dict, tz_offset_hours: float = 0.0, frame=None
) -> list[Suggestion]:
    """Propose fixes for every column the engine cannot model.

    Returns proposals only. Nothing is applied here; `apply_suggestions` does that, and
    only for the ones a caller explicitly names.
    """
    supported = set(capabilities.get("supported_types", []))
    if not supported:
        return []

    modelled = {SemanticRole.LEARNED, SemanticRole.RULE}
    existing = {c.name for c in table.columns}
    suggestions: list[Suggestion] = []

    for column in table.columns:
        if column.role not in modelled or column.type.value in supported:
            continue
        if column.type in TEMPORAL_TYPES:
            suggestion = _temporal_rewrite(
                column, supported, existing, tz_offset_hours, frame
            )
            if suggestion is not None:
                existing.update(c.name for c in suggestion.adds)
                suggestions.append(suggestion)

    return suggestions


def _temporal_rewrite(
    column: Column,
    supported: set[str],
    existing: set[str],
    tz_offset_hours: float,
    frame=None,
) -> Suggestion | None:
    """Split a timestamp into learnable parts and rebuild it from them."""
    if ColumnType.NUMBER.value not in supported:
        return None  # the engine cannot hold the extracted features either

    base = column.name
    anchor_value = _anchor_for(base, frame, tz_offset_hours)
    # A date carries no time of day: every value sits at midnight, so an extracted hour
    # would be a constant. A generator handed a zero-variance column does not merely
    # learn nothing from it — arfpy fails outright, fitting a truncated normal with a
    # scale of zero. Only a timestamp gets an hour.
    with_hour = column.type == ColumnType.TIMESTAMP

    weekday_name = _unique(f"{base}_weekday", existing)
    anchor_name = _unique(f"{base}_anchor", existing)
    hour_name = _unique(f"{base}_hour", existing) if with_hour else None

    adds = [
        Column(
            name=weekday_name,
            type=ColumnType.INTEGER,
            role=SemanticRole.LEARNED,
            minimum=0,
            maximum=6,
            description=f"day of week extracted from '{base}' (0 = Monday)",
            source_expression=Expr.model_validate(
                {"op": "day_of_week", "args": [{"col": base}], "tz_offset_hours": tz_offset_hours}
            ),
            provenance=_proposed(
                f"extracted from '{base}' so the engine can model weekly pattern"
            ),
        ),
        Column(
            name=anchor_name,
            type=column.type,
            role=SemanticRole.CONSTANT,
            constant_value=anchor_value,
            description=f"week beginning {anchor_value}, used to rebuild '{base}'",
            provenance=_proposed(
                f"the Monday of the first week seen in '{base}'. Rebuilt values fall "
                "within this one week, so they keep day of week (and time of day where "
                "there is one) but not the original calendar date."
            ),
        ),
    ]

    if with_hour:
        adds.insert(
            0,
            Column(
                name=hour_name,
                type=ColumnType.NUMBER,
                role=SemanticRole.LEARNED,
                minimum=0.0,
                maximum=24.0,
                description=f"hour of day extracted from '{base}'",
                source_expression=Expr.model_validate(
                    {
                        "op": "time_of_day",
                        "args": [{"col": base}],
                        "tz_offset_hours": tz_offset_hours,
                    }
                ),
                provenance=_proposed(
                    f"extracted from '{base}' so the engine can model time of day"
                ),
            ),
        )

    # Every extracted feature is put back. Learning one and then discarding it at
    # reconstruction would make the model's effort invisible.
    place_day = {"op": "add_days", "args": [{"col": anchor_name}, {"col": weekday_name}]}
    rebuild = Expr.model_validate(
        {"op": "add_hours", "args": [place_day, {"op": "sub", "args": [{"col": hour_name}, {"const": tz_offset_hours}]}]}
        if with_hour
        else place_day
    )

    kept = "time of day and day of week" if with_hour else "day of week"
    return Suggestion(
        column=base,
        kind="temporal_features",
        title=f"Model '{base}' as time features",
        rationale=(
            f"'{base}' is a {column.type.value}, which this engine cannot model. Its "
            f"{kept} can be learned as ordinary numbers, and '{base}' is then rebuilt "
            f"from them. The rebuilt column keeps {kept} but falls inside a single "
            f"reference week, so use it for working-pattern behaviour rather than as a "
            f"real calendar date."
        ),
        adds=adds,
        replaces_role=SemanticRole.DERIVED,
        replaces_formula=rebuild,
    )


def _anchor_for(column_name: str, frame, tz_offset_hours: float = 0) -> str:
    """The Monday of the first week present in the source, as an ISO string.

    Anchoring to the data's own start keeps rebuilt timestamps in a plausible period
    instead of an arbitrary one. Falling back to a fixed date when no source is at hand
    is itself an assumption, which is why the anchor column is labelled as proposed.
    """
    fallback = "2026-01-05T00:00:00+00:00"  # a Monday
    if frame is None or column_name not in getattr(frame, "columns", []):
        return fallback
    import pandas as pd

    stamps = pd.to_datetime(frame[column_name], format="mixed", utc=True, errors="coerce")
    earliest = (stamps + pd.Timedelta(hours=tz_offset_hours)).min()
    if pd.isna(earliest):
        return fallback
    monday = (earliest - pd.Timedelta(days=int(earliest.dayofweek))).normalize()
    return monday.isoformat()


def _unique(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    index = 2
    while f"{name}_{index}" in taken:
        index += 1
    return f"{name}_{index}"


def apply_suggestions(
    table: Table, suggestions: list[Suggestion], accept: set[str] | None = None
) -> Table:
    """Apply the named suggestions to a copy of the table.

    `accept` names the columns whose suggestions are being taken; passing None accepts
    all of them. The caller decides — this module never applies anything on its own.
    """
    result = table.model_copy(deep=True)

    for suggestion in suggestions:
        if accept is not None and suggestion.column not in accept:
            continue
        target = result.column(suggestion.column)
        if target is None:
            continue

        for addition in suggestion.adds:
            if result.column(addition.name) is None:
                result.columns.append(addition.model_copy(deep=True))

        if suggestion.replaces_role is not None:
            target.role = suggestion.replaces_role
        if suggestion.replaces_formula is not None:
            target.formula = suggestion.replaces_formula
        target.provenance = _proposed(
            f"rewritten by the '{suggestion.kind}' suggestion; confirm before relying on it"
        )

    return _ordered(result)


def _ordered(table: Table) -> Table:
    """Put constants first so derived columns can reference them.

    Derivation order is resolved by dependency rather than position, so this is for the
    reader: a rebuilt timestamp makes more sense next to the anchor it is built from.
    """
    rank = {
        SemanticRole.CONSTANT: 0,
        SemanticRole.IDENTIFIER: 1,
        SemanticRole.RULE: 2,
        SemanticRole.LEARNED: 3,
        SemanticRole.DERIVED: 4,
        SemanticRole.EMPTY: 5,
    }
    table.columns.sort(key=lambda c: rank.get(c.role, 9))
    return table


def prepare_source(frame, table: Table):
    """Materialise every column that declares a `source_expression`.

    A rewrite adds feature columns that do not exist in the uploaded file yet, so the
    source needs them before an engine can learn them. The expression is read from the
    specification rather than inferred, so a re-run rebuilds exactly the same features.
    """
    from .derive import evaluate

    result = frame.copy()
    for column in table.columns:
        if column.source_expression is None or column.name in result.columns:
            continue
        values = evaluate(column.source_expression, result)
        if column.type == ColumnType.INTEGER:
            import pandas as pd

            values = pd.to_numeric(values, errors="coerce")
        result[column.name] = values
    return result
