"""Schema-only generation: Faker plus an explicit declared rule per column.

Nothing here is learned. Every distribution in the output is one somebody wrote down,
which is exactly why this path needs no source records and carries no disclosure risk
— and equally why a model trained on its output has learned the author's assumptions
rather than a fact about any population.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from faker import Faker

from ..spec import Column, ColumnType, Rule, RuleKind, SemanticRole, SyntheticDataSpec, Table
from .base import (
    EngineAdapter,
    GenerationOutcome,
    apply_identifiers_and_constants,
    normalize,
    order_columns,
    register,
)


@register
class RuleEngine(EngineAdapter):
    name = "rules"

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "label": "Rules + Faker",
            "description": "Generates structurally valid data from declared rules, with no source records.",
            "single_table": True,
            "multi_table": False,
            "learns_from_records": False,
            "schema_only": True,
            "conditional_sampling": False,
            "cross_table_constraints": False,
            "privacy_mechanism": "none",
            "constraints": [
                "unique", "less_or_equal", "product_equals", "sum_equals",
                "not_null", "in_set", "range", "implies_null",
            ],
            "supported_types": [t.value for t in ColumnType],
        }

    def generate(
        self,
        spec: SyntheticDataSpec,
        table: Table,
        rows: int,
        source: pd.DataFrame | None = None,
    ) -> GenerationOutcome:
        started = time.perf_counter()
        rng = np.random.default_rng(spec.seed)
        faker = Faker()
        faker.seed_instance(spec.seed)
        warnings: list[str] = []

        data: dict[str, object] = {}
        for column in table.columns:
            if column.role in (SemanticRole.DERIVED, SemanticRole.CONSTANT, SemanticRole.EMPTY, SemanticRole.AGGREGATE):
                continue
            if column.role == SemanticRole.IDENTIFIER:
                continue  # filled by apply_identifiers_and_constants
            if column.rule is None:
                warnings.append(
                    f"Column '{column.name}' has no rule; emitting nulls. Declare a rule "
                    "or mark the column derived."
                )
                data[column.name] = [None] * rows
                continue
            data[column.name] = _sample(column, column.rule, rows, rng, faker)

        frame = pd.DataFrame(data, index=range(rows))
        frame = apply_identifiers_and_constants(frame, table, spec.seed)

        # Optional missingness, applied after values exist so the fraction is exact.
        for column in table.columns:
            if column.nullable and column.null_fraction > 0 and column.name in frame:
                n_null = int(round(column.null_fraction * rows))
                if n_null:
                    idx = rng.choice(rows, size=n_null, replace=False)
                    frame.loc[idx, column.name] = None

        frame, repair_info = normalize(frame, table)
        frame = order_columns(frame, table)

        return GenerationOutcome(
            frame=frame,
            engine=self.name,
            requested_rows=rows,
            generated_rows=len(frame),
            settings={"seed": spec.seed, "faker_locale": "en_US"},
            warnings=warnings,
            repairs=repair_info["repairs"],
            repaired_row_fraction=repair_info["repaired_row_fraction"],
            raw_invalid_row_fraction=repair_info["raw_invalid_row_fraction"],
            elapsed_seconds=time.perf_counter() - started,
        )


def _sample(column: Column, rule: Rule, rows: int, rng: np.random.Generator, faker: Faker):
    kind = rule.kind

    if kind == RuleKind.FAKER:
        provider = rule.provider or "word"
        if not hasattr(faker, provider):
            raise ValueError(f"unknown Faker provider '{provider}' for column '{column.name}'")
        method = getattr(faker, provider)
        return [method() for _ in range(rows)]

    if kind == RuleKind.SEQUENCE:
        prefix = rule.prefix or ""
        start = int(rule.start or 0)
        return [f"{prefix}{i:06d}" for i in range(start, start + rows)]

    if kind == RuleKind.UUID4:
        from .base import random_uuids

        return random_uuids(rows, rng)

    if kind == RuleKind.CHOICE:
        if not rule.values:
            raise ValueError(f"choice rule for '{column.name}' has no values")
        weights = np.asarray(rule.weights, dtype=float) if rule.weights else None
        if weights is not None:
            if len(weights) != len(rule.values):
                raise ValueError(
                    f"choice rule for '{column.name}' has {len(weights)} weights for "
                    f"{len(rule.values)} values"
                )
            weights = weights / weights.sum()
        return rng.choice(np.asarray(rule.values, dtype=object), size=rows, p=weights)

    if kind == RuleKind.INTEGER_RANGE:
        low = int(rule.start if rule.start is not None else 0)
        high = int(rule.end if rule.end is not None else 100)
        return rng.integers(low, high + 1, size=rows)

    if kind == RuleKind.NUMBER_RANGE:
        low = float(rule.start if rule.start is not None else 0.0)
        high = float(rule.end if rule.end is not None else 1.0)
        values = rng.uniform(low, high, size=rows)
        return np.round(values, rule.decimals) if rule.decimals is not None else values

    if kind == RuleKind.NORMAL:
        values = rng.normal(rule.mean or 0.0, rule.stddev or 1.0, size=rows)
        return np.round(values, rule.decimals) if rule.decimals is not None else values

    if kind in (RuleKind.DATE_RANGE, RuleKind.TIMESTAMP_RANGE):
        start = pd.Timestamp(rule.start or "2024-01-01")
        end = pd.Timestamp(rule.end or "2025-12-31")
        span = (end - start).total_seconds()
        offsets = rng.uniform(0, max(span, 0.0), size=rows)
        stamps = pd.to_datetime(start) + pd.to_timedelta(offsets, unit="s")
        if kind == RuleKind.DATE_RANGE:
            return stamps.normalize()
        return stamps

    if kind == RuleKind.AR1:
        # An explicitly invented autoregressive series, useful for sensor-style
        # scenarios. It is a stated assumption, not a learned temporal model.
        phi = rule.phi if rule.phi is not None else 0.9
        mean = rule.mean if rule.mean is not None else 0.0
        sigma = rule.stddev if rule.stddev is not None else 1.0
        series = np.empty(rows, dtype=float)
        series[0] = mean
        for i in range(1, rows):
            series[i] = mean + phi * (series[i - 1] - mean) + rng.normal(0, sigma)
        if column.minimum is not None or column.maximum is not None:
            series = np.clip(series, column.minimum, column.maximum)
        return np.round(series, rule.decimals) if rule.decimals is not None else series

    raise ValueError(f"rule kind '{kind}' is not implemented")
