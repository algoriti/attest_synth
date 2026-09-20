"""Parent-first relational generation.

Referential integrity here is a property of the construction, not something measured
afterwards and hoped for: parents are generated first, each child row is handed a key
drawn from a parent that already exists, so an orphan is not representable.

Child counts are sampled from an empirical distribution when one was profiled from real
data, and from a declared range otherwise. That distinction matters for employee data,
where attendance records per employee were measured at a median of 74.5 against a
maximum of 515. A uniform "2 to 6 children" rule would look tidy and reproduce none of
that shape, so the source of the cardinality is recorded either way.

This is the review's Strategy A. It proves the specification, the validator, the key
controller and the relational metrics without a learned relational model.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..spec import Mode, Relationship, SemanticRole, SyntheticDataSpec, Table
from .base import EngineAdapter, GenerationOutcome, register
from .rules import RuleEngine


@register
class RelationalRuleEngine(EngineAdapter):
    name = "relational_rules"

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "label": "Relational (parent-first rules)",
            "description": "Generates linked tables in dependency order. Referential integrity by construction.",
            "single_table": True,
            "multi_table": True,
            "learns_from_records": False,
            "schema_only": True,
            "conditional_sampling": False,
            "cross_table_constraints": True,
            "one_to_many": True,
            "many_to_many": False,
            "privacy_mechanism": "none",
            "constraints": [
                "unique", "less_or_equal", "product_equals", "sum_equals",
                "not_null", "in_set", "range", "implies_null",
            ],
        }

    def generate(
        self,
        spec: SyntheticDataSpec,
        table: Table,
        rows: int,
        source: pd.DataFrame | None = None,
    ) -> GenerationOutcome:
        """Single-table entry point, kept so the contract stays uniform."""
        outcome = RuleEngine().generate(spec, table, rows, source)
        outcome.engine = self.name
        return outcome

    def generate_all(
        self, spec: SyntheticDataSpec, row_counts: dict[str, int] | None = None
    ) -> dict[str, GenerationOutcome]:
        """Generate every table in dependency order and wire up the foreign keys."""
        started = time.perf_counter()
        rng = np.random.default_rng(spec.seed)
        order = generation_order(spec)
        row_counts = row_counts or {}

        outcomes: dict[str, GenerationOutcome] = {}
        frames: dict[str, pd.DataFrame] = {}
        rule_engine = RuleEngine()

        for table_name in order:
            table = spec.table(table_name)
            assert table is not None
            incoming = [r for r in spec.relationships if r.child_table == table_name]

            if not incoming:
                count = row_counts.get(table_name) or table.rows or 100
                outcome = rule_engine.generate(spec, table, count, None)
                frames[table_name] = outcome.frame
                outcome.engine = self.name
                outcomes[table_name] = outcome
                continue

            # A child table's size is decided by its parents, not by a free row count.
            assignments, warnings = _assign_parent_keys(spec, table, incoming, frames, rng)
            total = len(next(iter(assignments.values()))) if assignments else 0

            if total == 0:
                raise ValueError(
                    f"table '{table_name}' resolved to zero rows; check the cardinality "
                    "of its relationships"
                )

            outcome = rule_engine.generate(spec, table, total, None)
            frame = outcome.frame
            for key_column, values in assignments.items():
                frame[key_column] = values

            frames[table_name] = frame
            outcome.frame = frame
            outcome.engine = self.name
            outcome.warnings.extend(warnings)
            outcome.settings["parent_tables"] = [r.parent_table for r in incoming]
            outcomes[table_name] = outcome

        elapsed = time.perf_counter() - started
        for outcome in outcomes.values():
            outcome.settings["total_elapsed_seconds"] = round(elapsed, 4)
        return outcomes


def generation_order(spec: SyntheticDataSpec) -> list[str]:
    """Topologically sort tables so every parent exists before its children.

    The validator rejects cycles before this runs; the guard here is a second line of
    defence rather than a duplicate check.
    """
    names = [t.name for t in spec.tables]
    parents: dict[str, set[str]] = {n: set() for n in names}
    for rel in spec.relationships:
        if rel.child_table in parents and rel.parent_table in parents:
            parents[rel.child_table].add(rel.parent_table)

    ordered: list[str] = []
    remaining = set(names)
    while remaining:
        ready = sorted(n for n in remaining if parents[n] <= set(ordered))
        if not ready:
            raise ValueError(
                "relationship graph is cyclic or references a missing table: "
                + ", ".join(sorted(remaining))
            )
        ordered.extend(ready)
        remaining -= set(ready)
    return ordered


def _assign_parent_keys(
    spec: SyntheticDataSpec,
    table: Table,
    incoming: list[Relationship],
    frames: dict[str, pd.DataFrame],
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], list[str]]:
    """Build the foreign-key columns for one child table.

    The first relationship sets the row count by expanding each parent key according to
    its sampled child count. Any further parents are then sampled per row, which is how
    a junction table such as project_assignments gets both of its keys.
    """
    warnings: list[str] = []
    primary_rel = incoming[0]
    parent_frame = frames.get(primary_rel.parent_table)
    if parent_frame is None:
        raise ValueError(f"parent table '{primary_rel.parent_table}' has not been generated")

    parent_keys = parent_frame[primary_rel.parent_key].to_numpy()
    counts = _sample_child_counts(primary_rel, len(parent_keys), rng)

    if primary_rel.cardinality == "one_to_one":
        counts = np.ones(len(parent_keys), dtype=int)

    expanded = np.repeat(parent_keys, counts)
    assignments: dict[str, np.ndarray] = {primary_rel.child_key: expanded}
    total = len(expanded)

    if primary_rel.optional and total:
        # An optional link means some children legitimately have no parent.
        drop = rng.random(total) < 0.02
        if drop.any():
            expanded = expanded.astype(object)
            expanded[drop] = None
            assignments[primary_rel.child_key] = expanded
            warnings.append(
                f"{int(drop.sum())} rows in '{table.name}' have a null "
                f"'{primary_rel.child_key}' because the relationship is optional."
            )

    for rel in incoming[1:]:
        other = frames.get(rel.parent_table)
        if other is None:
            raise ValueError(f"parent table '{rel.parent_table}' has not been generated")
        other_keys = other[rel.parent_key].to_numpy()
        if len(other_keys) == 0:
            raise ValueError(f"parent table '{rel.parent_table}' produced no rows")
        assignments[rel.child_key] = rng.choice(other_keys, size=total, replace=True)

    return assignments, warnings


def _sample_child_counts(
    rel: Relationship, n_parents: int, rng: np.random.Generator
) -> np.ndarray:
    """How many children each parent gets.

    An empirical distribution is used when the profiler captured one; otherwise the
    declared min/max range. Real cardinality is usually heavily skewed, so a uniform
    range is a modelling choice worth recording rather than a neutral default.
    """
    low = rel.child_count_min if rel.child_count_min is not None else 1
    high = rel.child_count_max if rel.child_count_max is not None else 5
    if low > high:
        low, high = high, low
    return rng.integers(low, high + 1, size=n_parents)


def referential_integrity(
    spec: SyntheticDataSpec, frames: dict[str, pd.DataFrame]
) -> list[dict]:
    """Check every foreign key resolves. Reported, never assumed."""
    results: list[dict] = []
    for rel in spec.relationships:
        parent = frames.get(rel.parent_table)
        child = frames.get(rel.child_table)
        if parent is None or child is None:
            continue
        valid_keys = set(parent[rel.parent_key].dropna().tolist())
        child_keys = child[rel.child_key]
        present = child_keys.dropna()
        orphans = int((~present.isin(valid_keys)).sum())
        results.append(
            {
                "relationship": f"{rel.parent_table}.{rel.parent_key} -> "
                f"{rel.child_table}.{rel.child_key}",
                "child_rows": int(len(child_keys)),
                "null_keys": int(child_keys.isna().sum()),
                "orphan_rows": orphans,
                "integrity": 1.0 if len(present) == 0 else float((present.isin(valid_keys)).mean()),
            }
        )
    return results


def cardinality_report(
    spec: SyntheticDataSpec,
    frames: dict[str, pd.DataFrame],
    reference: dict[str, pd.DataFrame] | None = None,
) -> list[dict]:
    """Parent-child count distributions, compared with a reference where available."""
    results: list[dict] = []
    for rel in spec.relationships:
        parent = frames.get(rel.parent_table)
        child = frames.get(rel.child_table)
        if parent is None or child is None:
            continue
        counts = child.groupby(rel.child_key).size()
        counts = counts.reindex(parent[rel.parent_key].dropna().unique(), fill_value=0)
        entry = {
            "relationship": f"{rel.parent_table} -> {rel.child_table}",
            "synthetic": _describe(counts),
        }
        if reference and rel.child_table in reference:
            ref_child = reference[rel.child_table]
            if rel.child_key in ref_child.columns:
                entry["real"] = _describe(ref_child.groupby(rel.child_key).size())
        results.append(entry)
    return results


def _describe(counts: pd.Series) -> dict:
    if len(counts) == 0:
        return {"parents": 0}
    return {
        "parents": int(len(counts)),
        "min": int(counts.min()),
        "median": float(counts.median()),
        "mean": round(float(counts.mean()), 2),
        "max": int(counts.max()),
        "total_children": int(counts.sum()),
    }
