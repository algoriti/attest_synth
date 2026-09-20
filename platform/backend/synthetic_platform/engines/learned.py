"""Learned single-table engines: adversarial random forests, plus an honest baseline.

ARF was selected for the first learned adapter on three grounds measured in this
repository's benchmark: it is MIT licensed, it has a small integration surface, and it
held roughly 93% of real-data utility on the banking task (0.286 AP against 0.306). It
was not the strongest method on every task and it provides no privacy.

The independent sampler exists as a lower bound. It matches every column's marginal
distribution while destroying the relationships between them — on the education task
it scored 3.967 MAE against real data's 0.994. Keeping it available means a report can
always show what "good marginals, useless data" actually looks like.
"""
from __future__ import annotations

import time
import warnings as _warnings

import numpy as np
import pandas as pd

from ..spec import ColumnType, SemanticRole, SyntheticDataSpec, Table
from .base import (
    EngineAdapter,
    GenerationOutcome,
    apply_identifiers_and_constants,
    modellable_columns,
    normalize,
    order_columns,
    register,
)


def _prepare_source(table: Table, source: pd.DataFrame) -> pd.DataFrame:
    """Reduce the source to exactly the columns an engine is allowed to model."""
    wanted = [c.name for c in modellable_columns(table) if c.name in source.columns]
    if not wanted:
        raise ValueError(
            "no modellable columns found in the source; every column is an identifier, "
            "derived, constant or empty"
        )
    return source[wanted].copy()


def _categorical_names(table: Table) -> list[str]:
    return [
        c.name
        for c in modellable_columns(table)
        if c.type in (ColumnType.CATEGORY, ColumnType.BOOLEAN, ColumnType.STRING)
    ]


class ArfLeafDegeneracyError(RuntimeError):
    """arfpy could not fit a distribution to one of its own leaves."""


def _translate_arf_failure(
    exc: ValueError, frame: pd.DataFrame, min_node_size: int
) -> Exception:
    """Turn an opaque upstream failure into something a reader can act on.

    arfpy fits a truncated normal per numeric column per leaf. When a leaf ends up
    holding a single distinct value for a column, the scale is zero and SciPy raises a
    bare "Domain error in arguments" naming neither the library, the column nor the
    cause. It becomes more likely as rows and correlated columns increase, because the
    forest splits further.
    """
    if "scale" not in str(exc) and "Domain error" not in str(exc):
        return exc

    numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    coarse = sorted(
        ((int(frame[c].nunique(dropna=True)), c) for c in numeric), key=lambda p: p[0]
    )[:3]
    detail = ", ".join(f"'{name}' ({levels} distinct)" for levels, name in coarse)

    return ArfLeafDegeneracyError(
        "The adversarial random forest split the data until one of its leaves held a "
        f"single distinct value for a numeric column, which it cannot fit a "
        f"distribution to (min_node_size={min_node_size}). The columns with the fewest "
        f"distinct values are the usual cause: {detail}. Either raise the engine's "
        "minimum leaf size, mark a low-cardinality numeric column as a category so it "
        "is modelled as a factor, or drop a column that duplicates another."
    )


@register
class ArfEngine(EngineAdapter):
    name = "arf"

    #: Leaf sizes to try, in order. arfpy fails on a leaf holding a single distinct
    #: value for a numeric column, and the failure is not monotonic in either row count
    #: or leaf size: on the attendance features, 16,000 rows failed at leaf size 5 and
    #: succeeded at 20, while 28,549 rows did the opposite. Coarsening is therefore not
    #: a fix, and pinning a larger value only trades one failing configuration for
    #: another. The ladder works because a failing rung is uncorrelated with a
    #: succeeding one, which is also why every move is disclosed in the report.
    leaf_size_ladder = (5, 20, 50)

    def __init__(self) -> None:
        self._diagnostics: dict = {}

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "label": "Adversarial Random Forest",
            "description": "Learns a single table from approved records. MIT licensed, CPU only, no privacy guarantee.",
            "single_table": True,
            "multi_table": False,
            "learns_from_records": True,
            "schema_only": False,
            "conditional_sampling": False,
            "cross_table_constraints": False,
            "privacy_mechanism": "none",
            "constraints": [
                "unique", "less_or_equal", "product_equals", "sum_equals",
                "not_null", "in_set", "range", "implies_null",
            ],
            "supported_types": [
                ColumnType.INTEGER.value, ColumnType.NUMBER.value,
                ColumnType.CATEGORY.value, ColumnType.BOOLEAN.value,
                ColumnType.STRING.value,
            ],
            # arfpy converts every object column to a pandas category and models it as a
            # factor. Cost grows roughly with the square of the level count, so a column
            # with thousands of distinct values does not fail — it runs for minutes and
            # then produces a model that can only emit values it has already seen.
            "max_category_levels": 1000,
        }

    def generate(
        self,
        spec: SyntheticDataSpec,
        table: Table,
        rows: int,
        source: pd.DataFrame | None = None,
    ) -> GenerationOutcome:
        if source is None:
            raise ValueError("the ARF engine requires approved source records")

        from arfpy import arf

        started = time.perf_counter()
        collected: list[str] = []
        prepared = _prepare_source(table, source)
        categoricals = [c for c in _categorical_names(table) if c in prepared.columns]

        frame_in = prepared.copy()
        for name in categoricals:
            frame_in[name] = frame_in[name].astype("category")

        num_trees = 30
        ladder = list(self.leaf_size_ladder)
        retries: list[str] = []
        model = raw = None
        min_node_size = ladder[0]

        for attempt, min_node_size in enumerate(ladder):
            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always")
                try:
                    model = arf.arf(
                        frame_in,
                        num_trees=num_trees,
                        max_iters=3,
                        min_node_size=min_node_size,
                        verbose=False,
                        random_state=spec.seed,
                        n_jobs=1,
                    )
                    model.forde()
                    raw = model.forge(rows)
                except ValueError as exc:
                    translated = _translate_arf_failure(exc, frame_in, min_node_size)
                    if not isinstance(translated, ArfLeafDegeneracyError):
                        raise translated from exc
                    if attempt == len(ladder) - 1:
                        raise translated from exc
                    retries.append(
                        f"Minimum leaf size {min_node_size} produced a leaf the engine "
                        f"could not fit a distribution to; retried with "
                        f"{ladder[attempt + 1]}."
                    )
                    continue
                collected = sorted({str(w.message) for w in caught})
            break

        assert model is not None and raw is not None

        # arfpy reports one out-of-bag accuracy per adversarial iteration.
        accuracy = getattr(model, "acc", None)
        if isinstance(accuracy, (list, tuple, np.ndarray)):
            accuracy_history = [float(a) for a in accuracy]
            final_accuracy = accuracy_history[-1] if accuracy_history else float("nan")
        else:
            accuracy_history = []
            final_accuracy = float(accuracy) if accuracy is not None else float("nan")

        self._diagnostics = {
            "discriminator_oob_accuracy": final_accuracy,
            "discriminator_oob_accuracy_history": accuracy_history,
            "num_trees": num_trees,
            "note": (
                "Discriminator accuracy near 0.5 means the forest could not separate real "
                "from synthetic rows on its own criterion. It is the generator's own "
                "diagnostic, not an independent quality measure."
            ),
        }

        frame = pd.DataFrame(raw).reset_index(drop=True)
        frame = apply_identifiers_and_constants(frame, table, spec.seed)
        frame, repair_info = normalize(frame, table, reference=prepared)
        frame = order_columns(frame, table)

        return GenerationOutcome(
            frame=frame,
            engine=self.name,
            requested_rows=rows,
            generated_rows=len(frame),
            settings={
                "num_trees": num_trees,
                "max_iters": 3,
                "min_node_size": min_node_size,
                "seed": spec.seed,
                "modelled_columns": list(prepared.columns),
                **self._diagnostics,
            },
            warnings=retries + collected,
            repairs=repair_info["repairs"],
            repaired_row_fraction=repair_info["repaired_row_fraction"],
            raw_invalid_row_fraction=repair_info["raw_invalid_row_fraction"],
            elapsed_seconds=time.perf_counter() - started,
        )

    def diagnostics(self) -> dict:
        return dict(self._diagnostics)


@register
class IndependentEngine(EngineAdapter):
    """Samples each column independently. A deliberate lower bound, never a product."""

    name = "independent"

    def capabilities(self) -> dict:
        return {
            "name": self.name,
            "label": "Independent columns (baseline)",
            "description": "Samples each column separately. Matches marginals, destroys relationships. Baseline only.",
            "single_table": True,
            "multi_table": False,
            "learns_from_records": True,
            "schema_only": False,
            "conditional_sampling": False,
            "cross_table_constraints": False,
            "privacy_mechanism": "none",
            "constraints": [
                "unique", "less_or_equal", "product_equals", "sum_equals",
                "not_null", "in_set", "range", "implies_null",
            ],
            "supported_types": [t.value for t in ColumnType],
            "baseline": True,
        }

    def generate(
        self,
        spec: SyntheticDataSpec,
        table: Table,
        rows: int,
        source: pd.DataFrame | None = None,
    ) -> GenerationOutcome:
        if source is None:
            raise ValueError("the independent baseline requires approved source records")

        started = time.perf_counter()
        rng = np.random.default_rng(spec.seed)
        prepared = _prepare_source(table, source)

        frame = pd.DataFrame(
            {name: rng.choice(prepared[name].to_numpy(), rows) for name in prepared.columns}
        )
        frame = apply_identifiers_and_constants(frame, table, spec.seed)
        frame, repair_info = normalize(frame, table, reference=prepared)
        frame = order_columns(frame, table)

        return GenerationOutcome(
            frame=frame,
            engine=self.name,
            requested_rows=rows,
            generated_rows=len(frame),
            settings={"seed": spec.seed, "modelled_columns": list(prepared.columns)},
            warnings=[
                "Independent sampling preserves no relationship between columns. It is a "
                "diagnostic lower bound, not a usable synthesis method."
            ],
            repairs=repair_info["repairs"],
            repaired_row_fraction=repair_info["repaired_row_fraction"],
            raw_invalid_row_fraction=repair_info["raw_invalid_row_fraction"],
            elapsed_seconds=time.perf_counter() - started,
        )
