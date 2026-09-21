"""Bounded parent-first generation. Final schema and relationship checks are independent.

Single-parent counts use declared uniform ranges. Two-parent junctions solve degree
bounds jointly; compound uniqueness is enforced when declared on the two foreign keys.
This is a rule engine, not learned relational synthesis.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..spec import Mode, Relationship, SemanticRole, SyntheticDataSpec, Table
from .base import EngineAdapter, GenerationOutcome, register
from .rules import RuleEngine


class RelationalFeasibilityError(ValueError):
    """A declared row count or cardinality range cannot jointly be satisfied.

    Every raise in this module using this type is a clean, human-authored message
    about a specification the person can fix — a row count that doesn't fit the
    declared child-count range, a junction whose two sides can't be reconciled, a
    solver that ran out of time. None of it is an engine bug. Giving these their own
    type lets the API present them as a rejected specification (message only, no
    traceback) instead of "the engine failed" with a Python stack trace, without
    changing what `run()` itself raises for direct callers.
    """


@register
class RelationalRuleEngine(EngineAdapter):
    name = "relational_rules"

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "label": "Relational (parent-first rules)",
            "description": "Generates linked tables in dependency order. Final keys and cardinalities independently checked.",
            "single_table": True,
            "multi_table": True,
            "learns_from_records": False,
            "schema_only": True,
            "conditional_sampling": False,
            "cross_table_constraints": True,
            "cross_table_operations": ["parent_child_less_or_equal", "parent_child_greater_or_equal"],
            "aggregates": ["count", "sum", "mean", "min", "max"],
            "one_to_many": True,
            "many_to_many": True,
            "max_parents_per_child": 2,
            "compound_junction_uniqueness": True,
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
                count = row_counts.get(table_name, table.rows if table.rows is not None else 100)
                outcome = rule_engine.generate(spec, table, count, None)
                frames[table_name] = outcome.frame
                outcome.engine = self.name
                outcomes[table_name] = outcome
                continue

            # A child table's size is decided by its parents, not by a free row count.
            assignments, warnings = _assign_parent_keys(spec, table, incoming, frames, rng)
            total = len(next(iter(assignments.values()))) if assignments else 0

            if total > 200000:
                raise RelationalFeasibilityError("Relationship expansion exceeds 200,000 rows per table.")

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
            raise RelationalFeasibilityError(
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
    if len(incoming) == 2:
        return _junction_keys(table, incoming, frames, rng), []
    rel = incoming[0]
    keys = frames[rel.parent_table][rel.parent_key].to_numpy()
    low = rel.child_count_min if rel.child_count_min is not None else (0 if rel.cardinality == "one_to_one" else 1)
    high = rel.child_count_max if rel.child_count_max is not None else (1 if rel.cardinality == "one_to_one" else 5)
    if rel.cardinality == "one_to_one": high = min(high, 1)
    if table.rows is None:
        counts = rng.integers(low, high + 1, size=len(keys))
        linked = int(counts.sum())
        nulls = round(linked * rel.null_fraction / (1 - rel.null_fraction))
    else:
        nulls = round(table.rows * rel.null_fraction)
        linked = table.rows - nulls
        counts = _bounded_counts(len(keys), low, high, linked, rng)
    if linked + nulls > 200000: raise RelationalFeasibilityError("Relationship expansion exceeds 200,000 rows.")
    expanded = np.repeat(keys, counts)
    if nulls: expanded = np.concatenate([expanded.astype(object), np.full(nulls, None)])
    rng.shuffle(expanded)
    return {rel.child_key: expanded}, []


def _bounded_counts(n, low, high, total, rng):
    if total < n * low or total > n * high:
        raise RelationalFeasibilityError(f"Infeasible child count: {total} requested; allowed {n*low}..{n*high}.")
    counts = np.full(n, low, dtype=int)
    left = total - n * low
    # Distribute remaining counts without allocating a huge repeated-key pool.
    while left:
        available = np.flatnonzero(counts < high)
        chosen = rng.choice(available, size=min(left, len(available)), replace=False)
        counts[chosen] += 1
        left -= len(chosen)
    return counts


def _junction_keys(table, incoming, frames, rng):
    from scipy.optimize import milp, Bounds, LinearConstraint
    from scipy.sparse import lil_matrix
    a,b = incoming
    ka,kb = (frames[r.parent_table][r.parent_key].to_numpy() for r in incoming)
    na,nb = len(ka),len(kb)
    if na*nb > 50000:
        raise RelationalFeasibilityError("This PoC supports junctions with at most 50,000 possible parent pairs.")
    def bounds(rel,n,first=False):
        lo = rel.child_count_min if rel.child_count_min is not None else (1 if first else 0)
        hi = rel.child_count_max if rel.child_count_max is not None else (5 if first else 200000)
        if rel.cardinality == 'one_to_one': hi = 1
        return lo,hi
    la,ha = bounds(a,na,True); lb,hb = bounds(b,nb)
    unique = any(set(k)=={a.child_key,b.child_key} for k in table.unique_keys)
    if unique: ha,hb = min(ha,nb),min(hb,na)
    lower,upper = max(na*la,nb*lb),min(na*ha,nb*hb,200000)
    if lower>upper: raise RelationalFeasibilityError("Infeasible junction cardinalities across the two parents.")
    total = table.rows if table.rows is not None else int(rng.integers(lower,upper+1))
    if total<lower or total>upper: raise RelationalFeasibilityError(f"Junction row count must be between {lower} and {upper}.")
    if not total:
        return {a.child_key:ka[:0],b.child_key:kb[:0]}
    if not na or not nb: raise RelationalFeasibilityError("Nonempty junction requires both parent tables.")
    matrix = lil_matrix((na+nb+1,na*nb))
    for i in range(na): matrix[i,i*nb:(i+1)*nb]=1
    for j in range(nb): matrix[na+j,j::nb]=1
    matrix[-1,:]=1
    solution = milp(rng.random(na*nb),integrality=np.ones(na*nb),
        bounds=Bounds(0,1 if unique else total),
        constraints=LinearConstraint(matrix.tocsr(),[la]*na+[lb]*nb+[total],[ha]*na+[hb]*nb+[total]),
        options={'time_limit':10})
    if not solution.success or solution.x is None:
        raise RelationalFeasibilityError("Could not satisfy junction bounds within the solver limit; reduce counts or relax the declared rules.")
    cells = np.repeat(np.arange(na*nb),np.rint(solution.x).astype(int))
    rng.shuffle(cells)
    return {a.child_key:ka[cells//nb],b.child_key:kb[cells%nb]}


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
