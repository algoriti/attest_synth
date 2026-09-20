"""The engine contract, plus the normalisation every engine's output passes through.

Engines are replaceable workers. The platform owns the specification, the validation,
the repair step and the evaluation; an engine only turns a prepared request into rows.
An engine never judges its own success.

Repair happens here rather than inside an adapter so the counts are comparable across
engines and end up in the evidence report either way. The benchmark that preceded this
platform recorded ARF repairing 100% of banking rows purely because it returns integer
fields as floats — a fact that stays invisible unless the wrapper reports it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..spec import Column, ColumnType, SemanticRole, SyntheticDataSpec, Table


@dataclass
class GenerationOutcome:
    """What an engine produced, including everything that went imperfectly.

    `requested_rows` versus `generated_rows` is deliberately explicit: a request for
    10,000 rows that yields 8,000 is an incomplete result, never a silent success.
    """

    frame: pd.DataFrame
    engine: str
    requested_rows: int
    generated_rows: int
    settings: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    repairs: dict[str, int] = field(default_factory=dict)
    repaired_row_fraction: float = 0.0
    raw_invalid_row_fraction: float = 0.0
    elapsed_seconds: float = 0.0
    derivation_trace: list[dict] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.generated_rows == self.requested_rows


class EngineAdapter(ABC):
    """Every generator implements this. Capabilities are declared, never assumed."""

    name: str = "abstract"

    @abstractmethod
    def capabilities(self) -> dict:
        """Declare what this engine can actually do.

        The validator uses this to reject unsupported requests before any work starts,
        which is what stops an LLM selecting relational mode on a single-table engine.
        """

    @abstractmethod
    def generate(
        self,
        spec: SyntheticDataSpec,
        table: Table,
        rows: int,
        source: pd.DataFrame | None = None,
    ) -> GenerationOutcome:
        """Produce `rows` rows for `table`."""

    def diagnostics(self) -> dict:
        return {}


# --- registry -------------------------------------------------------------------

_REGISTRY: dict[str, type[EngineAdapter]] = {}


def register(cls: type[EngineAdapter]) -> type[EngineAdapter]:
    _REGISTRY[cls.name] = cls
    return cls


def get_engine(name: str) -> EngineAdapter:
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "none registered"
        raise KeyError(f"unknown engine '{name}'; available: {known}")
    return _REGISTRY[name]()


def available_engines() -> list[dict]:
    return [cls().capabilities() for cls in _REGISTRY.values()]


def choose_engine(spec: SyntheticDataSpec) -> str:
    """Pick a default engine for a specification the user did not pin."""
    if spec.engine:
        return spec.engine
    from ..spec import Mode

    if spec.mode == Mode.RELATIONAL_RULES:
        return "relational_rules"
    if spec.mode == Mode.LEARNED_TABLE:
        return "arf" if "arf" in _REGISTRY else "independent"
    return "rules"


# --- shared normalisation --------------------------------------------------------

# Columns the generator never sees: identifiers are regenerated, derived values are
# computed afterwards, constants and empties carry no information to model.
GENERATOR_EXCLUDED_ROLES = {
    SemanticRole.IDENTIFIER,
    SemanticRole.DERIVED,
    SemanticRole.CONSTANT,
    SemanticRole.EMPTY,
}


def modellable_columns(table: Table) -> list[Column]:
    return [c for c in table.columns if c.role not in GENERATOR_EXCLUDED_ROLES]


def normalize(
    frame: pd.DataFrame, table: Table, reference: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, dict]:
    """Enforce declared types and bounds, counting every change.

    Unknown categories are a hard failure rather than a silent substitution: quietly
    swapping an invalid category would hide a real generator defect.
    """
    result = frame.copy().reset_index(drop=True)
    repairs: dict[str, int] = {}
    repaired_rows = np.zeros(len(result), dtype=bool)
    invalid_rows = np.zeros(len(result), dtype=bool)

    for column in table.columns:
        if column.name not in result.columns:
            continue
        series = result[column.name]

        if column.type in (ColumnType.INTEGER, ColumnType.NUMBER):
            values = pd.to_numeric(series, errors="coerce")
            low = column.minimum
            high = column.maximum
            if low is None and reference is not None and column.name in reference:
                low = pd.to_numeric(reference[column.name], errors="coerce").min()
            if high is None and reference is not None and column.name in reference:
                high = pd.to_numeric(reference[column.name], errors="coerce").max()

            nonfinite = ~np.isfinite(values.to_numpy(dtype=float)) & series.notna().to_numpy()
            if nonfinite.any():
                raise ValueError(
                    f"engine returned non-finite values in '{column.name}'"
                )

            fixed = values
            if low is not None or high is not None:
                fixed = values.clip(lower=low, upper=high)
            out_of_bounds = (values != fixed) & values.notna()

            rounded = fixed
            not_integral = pd.Series(False, index=result.index)
            if column.type == ColumnType.INTEGER:
                rounded = np.round(fixed)
                not_integral = (np.abs(fixed - rounded) > 1e-9) & fixed.notna()

            changed = (out_of_bounds | not_integral).fillna(False).to_numpy()
            if changed.any():
                repairs[column.name] = int(changed.sum())
                repaired_rows |= changed
            invalid_rows |= changed

            if column.type == ColumnType.INTEGER:
                if rounded.isna().any():
                    result[column.name] = rounded.astype("Int64")
                else:
                    result[column.name] = rounded.astype("int64")
            else:
                result[column.name] = rounded.astype(float)

        elif column.type == ColumnType.BOOLEAN:
            result[column.name] = series.astype(bool)

        elif column.type == ColumnType.CATEGORY:
            allowed = column.allowed_values
            if allowed is None and reference is not None and column.name in reference:
                allowed = reference[column.name].dropna().unique().tolist()
            if allowed is not None:
                valid = series.isna() | series.isin(allowed)
                if not valid.all():
                    unexpected = sorted(
                        {str(v) for v in series[~valid].unique()}
                    )[:5]
                    raise ValueError(
                        f"engine returned unknown categories in '{column.name}': "
                        f"{', '.join(unexpected)}"
                    )
    return result, {
        "repairs": repairs,
        "repaired_row_fraction": float(repaired_rows.mean()) if len(result) else 0.0,
        "raw_invalid_row_fraction": float(invalid_rows.mean()) if len(result) else 0.0,
    }


def random_uuids(count: int, rng: np.random.Generator) -> list[str]:
    """Seeded version 4 UUIDs.

    Built from two 64-bit draws because NumPy generators top out at 64 bits, then
    stamped with the version and variant bits so the results are valid v4 UUIDs.
    """
    import uuid

    high = rng.integers(0, 2**64, size=count, dtype=np.uint64)
    low = rng.integers(0, 2**64, size=count, dtype=np.uint64)
    out: list[str] = []
    for h, l in zip(high, low):
        value = (int(h) << 64) | int(l)
        value &= ~(0xF000 << 64)  # clear version nibble
        value |= 0x4000 << 64  # version 4
        value &= ~(0xC000 << 48)  # clear variant bits
        value |= 0x8000 << 48  # RFC 4122 variant
        out.append(str(uuid.UUID(int=value)))
    return out


def apply_identifiers_and_constants(
    frame: pd.DataFrame, table: Table, seed: int
) -> pd.DataFrame:
    """Fill identifier, constant and empty columns.

    Identifiers are always regenerated. Copying a source UUID into synthetic output
    would carry a real record's key into a dataset people believe is synthetic.
    """
    rng = np.random.default_rng(seed)
    result = frame.copy()

    for column in table.columns:
        if column.role == SemanticRole.IDENTIFIER:
            if column.type == ColumnType.UUID:
                result[column.name] = random_uuids(len(result), rng)
            elif column.type == ColumnType.INTEGER:
                result[column.name] = np.arange(1, len(result) + 1, dtype="int64")
            else:
                prefix = (column.rule.prefix if column.rule else "") or "ID-"
                result[column.name] = [f"{prefix}{i:06d}" for i in range(1, len(result) + 1)]
        elif column.role == SemanticRole.CONSTANT:
            result[column.name] = column.constant_value
        elif column.role == SemanticRole.EMPTY:
            result[column.name] = pd.NA

    return result


def order_columns(frame: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Return columns in the order the specification declares them."""
    declared = [c.name for c in table.columns if c.name in frame.columns]
    extra = [c for c in frame.columns if c not in declared]
    return frame[declared + extra]
