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

    column: str  # the column this suggestion is keyed on; the anchor of a group
    kind: str
    title: str
    rationale: str
    adds: list[Column] = field(default_factory=list)
    #: name -> (role, formula) for every column this suggestion rewrites. A group of
    #: related timestamps is rewritten together or not at all, because the followers
    #: are expressed as offsets from the anchor and are meaningless without it.
    rewrites: dict[str, tuple[SemanticRole, Expr]] = field(default_factory=dict)

    @property
    def covers(self) -> list[str]:
        return list(self.rewrites)

    def as_dict(self) -> dict:
        return {
            "column": self.column,
            "covers": self.covers,
            "kind": self.kind,
            "title": self.title,
            "rationale": self.rationale,
            "adds": [c.model_dump(mode="json") for c in self.adds],
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

    unsupported_temporal = [
        c for c in table.columns
        if c.role in modelled
        and c.type.value not in supported
        and c.type in TEMPORAL_TYPES
    ]

    # Related timestamps are rewritten as one unit. Rebuilding each independently
    # loses the ordering between them: a call log came back with the IVR leg starting
    # a day before its own call. Only the anchor is reconstructed from calendar
    # features; the rest become offsets from it, so the ordering holds by construction.
    for group in _temporal_groups(unsupported_temporal, frame):
        suggestion = _temporal_group_rewrite(
            group, supported, existing, tz_offset_hours, frame
        )
        if suggestion is not None:
            existing.update(c.name for c in suggestion.adds)
            suggestions.append(suggestion)

    return suggestions


def _temporal_groups(columns: list[Column], frame) -> list[list[Column]]:
    """Cluster temporal columns that describe the same episode, anchor first.

    Two timestamps belong together when their typical separation is small relative to
    the span of the data: a call and its IVR leg, a clock-in and its clock-out. A hire
    date and a call date do not, and forcing an offset between them would invent a
    relationship nobody claimed.

    Without a source frame there is nothing to measure, so every column stands alone
    and behaves exactly as it did before grouping existed.
    """
    if frame is None or len(columns) < 2:
        return [[c] for c in columns]

    import numpy as np
    import pandas as pd

    stamps: dict[str, pd.Series] = {}
    for column in columns:
        if column.name not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column.name], format="mixed", utc=True, errors="coerce")
        if parsed.notna().any():
            stamps[column.name] = parsed

    named = [c for c in columns if c.name in stamps]
    if len(named) < 2:
        return [[c] for c in columns]

    # Two timestamps describe the same episode when the *variation* in the gap between
    # them is small next to the variation in the timestamps themselves. A delivery
    # always follows its order by days, while orders spread over months, so the gap
    # barely moves by comparison. A date of birth against an application date moves as
    # much as the column does, because the two are independent quantities.
    #
    # This is scale-free, which a magnitude threshold is not: an earlier version asked
    # whether the gap was under 5% of the data's span, and split a 10-day delivery away
    # from its own order because the file happened to cover 90 days.
    def spread(values) -> float:
        series = pd.Series(values).dropna()
        if len(series) < 4:
            return float("nan")
        return float(series.quantile(0.75) - series.quantile(0.25))

    epoch = {name: stamps[name].astype("int64") / 1e9 for name in stamps}

    parent = {c.name: c.name for c in named}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(named):
        for b in named[i + 1:]:
            gap_spread = spread(epoch[b.name] - epoch[a.name])
            column_spread = min(spread(epoch[a.name]), spread(epoch[b.name]))
            if not (np.isfinite(gap_spread) and np.isfinite(column_spread)):
                continue
            if column_spread <= 0:
                # Every row shares one timestamp; fall back to whether the gap is
                # steady rather than comparing it to a spread of zero.
                same_episode = gap_spread <= 0
            else:
                same_episode = gap_spread <= column_spread
            if same_episode:
                parent[find(b.name)] = find(a.name)

    clusters: dict[str, list[Column]] = {}
    for column in named:
        clusters.setdefault(find(column.name), []).append(column)

    groups = [_anchor_first(members, stamps) for members in clusters.values()]
    groups.extend([c] for c in columns if c.name not in stamps)
    return groups


def _anchor_first(members: list[Column], stamps) -> list[Column]:
    """Order a whole group in time, earliest first.

    The first column becomes the anchor and each later one is expressed as an offset
    from the column immediately before it. Ordering the entire chain matters, not just
    the anchor: offsets taken from a common anchor are learned independently, so one
    row can still receive a larger offset for the earlier event. Chaining removes that
    possibility, because each step forward is its own non-negative quantity.
    """
    if len(members) == 1:
        return members

    # Order by how often each column precedes the others *within the same row*, not by
    # each column's own median. Over a two-year attendance export the column medians
    # put the clock-out half a day before the clock-in, because a few hours of
    # difference is noise next to the span; row by row, the clock-out is later every
    # single time.
    def precedes_others(column: Column) -> float:
        score = 0.0
        for other in members:
            if other.name == column.name:
                continue
            delta = (stamps[other.name] - stamps[column.name]).dt.total_seconds()
            comparable = delta.notna()
            if comparable.any():
                score += float((delta[comparable] >= 0).mean())
        return score

    return sorted(members, key=lambda c: (-precedes_others(c), c.name))


def _temporal_group_rewrite(
    group: list[Column],
    supported: set[str],
    existing: set[str],
    tz_offset_hours: float,
    frame=None,
) -> Suggestion | None:
    """Rebuild a group of related timestamps from one anchor plus offsets."""
    if ColumnType.NUMBER.value not in supported:
        return None  # the engine cannot hold the extracted features either

    anchor_column, followers = group[0], group[1:]
    base = anchor_column.name
    anchor_value = _anchor_for(base, frame, tz_offset_hours)

    # A date carries no time of day: every value sits at midnight, so an extracted hour
    # would be a constant. A generator handed a zero-variance column does not merely
    # learn nothing from it — arfpy fails outright, fitting a truncated normal with a
    # scale of zero. Only a timestamp gets an hour.
    with_hour = anchor_column.type == ColumnType.TIMESTAMP

    weekday_name = _unique(f"{base}_weekday", existing)
    reference_name = _unique(f"{base}_anchor", existing)
    hour_name = _unique(f"{base}_hour", existing) if with_hour else None
    existing = existing | {weekday_name, reference_name} | ({hour_name} if with_hour else set())

    adds = [
        Column(
            # A weekday is a category, not a quantity. Typed as an integer it is handed
            # to a tree-based engine as a continuous variable, which is wrong twice: it
            # implies Sunday is six units away from Monday rather than adjacent, and a
            # leaf holding a single weekday has zero variance, which arfpy cannot fit a
            # distribution to. As a category it is modelled as a factor instead.
            name=weekday_name,
            type=ColumnType.CATEGORY,
            role=SemanticRole.LEARNED,
            allowed_values=list(range(7)),
            description=f"day of week extracted from '{base}' (0 = Monday)",
            source_expression=Expr.model_validate(
                {"op": "day_of_week", "args": [{"col": base}], "tz_offset_hours": tz_offset_hours}
            ),
            provenance=_proposed(
                f"extracted from '{base}' so the engine can model weekly pattern"
            ),
        ),
        Column(
            name=reference_name,
            type=anchor_column.type,
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
    place_day = {"op": "add_days", "args": [{"col": reference_name}, {"col": weekday_name}]}
    anchor_rebuild = Expr.model_validate(
        {"op": "add_hours", "args": [place_day, {"op": "sub", "args": [{"col": hour_name}, {"const": tz_offset_hours}]}]}
        if with_hour
        else place_day
    )

    rewrites: dict[str, tuple[SemanticRole, Expr]] = {
        base: (SemanticRole.DERIVED, anchor_rebuild)
    }

    ordering_guaranteed = True
    unordered: list[str] = []

    previous = base
    for follower in followers:
        gap_name = _unique(f"{follower.name}_gap_seconds", existing)
        existing = existing | {gap_name}
        low, high, nullable, non_negative = _gap_bounds(previous, follower.name, frame)
        ordering_guaranteed &= non_negative
        if not non_negative:
            unordered.append(follower.name)

        adds.append(
            Column(
                name=gap_name,
                type=ColumnType.NUMBER,
                role=SemanticRole.LEARNED,
                minimum=low,
                maximum=high,
                nullable=nullable,
                description=f"seconds from '{previous}' to '{follower.name}'",
                source_expression=Expr.model_validate(
                    {"op": "duration_seconds", "args": [{"col": previous}, {"col": follower.name}]}
                ),
                provenance=_proposed(
                    f"'{follower.name}' is modelled as an offset from '{previous}' so the "
                    "two cannot be reconstructed out of order"
                ),
            )
        )
        rewrites[follower.name] = (
            SemanticRole.DERIVED,
            Expr.model_validate(
                {"op": "add_seconds", "args": [{"col": previous}, {"col": gap_name}]}
            ),
        )
        previous = follower.name

    kept = "time of day and day of week" if with_hour else "day of week"
    if followers:
        names = ", ".join(f"'{f.name}'" for f in followers)
        ordering = (
            f" Each offset is non-negative and measured from the timestamp before it, so "
            f"the whole sequence — '{base}', then {names} — can never come out of order."
            if ordering_guaranteed
            else (
                f" The source itself has {', '.join(unordered)} occurring before "
                f"'{base}' in some rows, so the offsets are allowed to be negative and "
                "the ordering is not guaranteed."
            )
        )
        title = f"Model '{base}' and {len(followers)} related timestamp(s) as time features"
        rationale = (
            f"'{base}' is a {anchor_column.type.value}, which this engine cannot model. "
            f"Its {kept} can be learned as ordinary numbers, and '{base}' is rebuilt from "
            f"them. {names} are modelled as elapsed seconds from '{base}' rather than "
            f"independently, then rebuilt by adding that offset back.{ordering} Rebuilt "
            f"values fall inside a single reference week, so use them for working-pattern "
            f"behaviour rather than as real calendar dates."
        )
    else:
        title = f"Model '{base}' as time features"
        rationale = (
            f"'{base}' is a {anchor_column.type.value}, which this engine cannot model. Its "
            f"{kept} can be learned as ordinary numbers, and '{base}' is then rebuilt "
            f"from them. The rebuilt column keeps {kept} but falls inside a single "
            f"reference week, so use it for working-pattern behaviour rather than as a "
            f"real calendar date."
        )

    return Suggestion(
        column=base,
        kind="temporal_features",
        title=title,
        rationale=rationale,
        adds=adds,
        rewrites=rewrites,
    )


def _gap_bounds(anchor: str, follower: str, frame) -> tuple[float | None, float | None, bool, bool]:
    """Observed bounds for the gap between two timestamps.

    Returns (minimum, maximum, nullable, non_negative). Clamping the minimum at zero is
    what makes the ordering hold — but only where the source supports it. If the real
    data has the follower occurring first in some rows, that is a fact about the data,
    and inventing an ordering it does not have would be the same overclaiming this
    platform exists to avoid.
    """
    if frame is None or anchor not in getattr(frame, "columns", []) or follower not in frame.columns:
        return 0.0, None, True, True

    import pandas as pd

    a = pd.to_datetime(frame[anchor], format="mixed", utc=True, errors="coerce")
    b = pd.to_datetime(frame[follower], format="mixed", utc=True, errors="coerce")
    gap = (b - a).dt.total_seconds()
    observed = gap.dropna()
    if observed.empty:
        return 0.0, None, True, True

    low, high = float(observed.min()), float(observed.max())
    non_negative = low >= 0
    return (0.0 if non_negative else low), high, bool(gap.isna().any()), non_negative


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
    all of them. Naming any column of a group accepts the whole group: the followers
    are offsets from the anchor and mean nothing without it. The caller decides — this
    module never applies anything on its own.
    """
    result = table.model_copy(deep=True)

    for suggestion in suggestions:
        if accept is not None and not (accept & {suggestion.column, *suggestion.covers}):
            continue

        for addition in suggestion.adds:
            if result.column(addition.name) is None:
                result.columns.append(addition.model_copy(deep=True))

        for name, (role, formula) in suggestion.rewrites.items():
            target = result.column(name)
            if target is None:
                continue
            target.role = role
            target.formula = formula
            target.provenance = _proposed(
                f"rewritten by the '{suggestion.kind}' suggestion; confirm before "
                "relying on it"
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
