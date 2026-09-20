"""SyntheticDataSpec: the contract every part of the platform agrees on.

The specification is the platform's stable interface. The UI, the LLM assistant and
the engines all read and write this object; none of them owns it. An engine may be
replaced without changing a stored specification.

Two ideas here carry most of the weight:

`SemanticRole` separates values that must be *regenerated* (identifiers), values that
carry no information (constant/empty), values *computed* from other columns (derived)
and values a generator may actually *learn*. Profiling real attendance data showed why
this matters: `extra_hours` there is round(shift_hours - 6) and `late_status` is
"clocked in after 07:45", to 99.2% and 97.6% agreement respectively. A learned
generator treats those as ordinary columns and happily emits a six-hour shift carrying
nine hours of overtime. Derived columns are computed after generation instead.

`Provenance` records where each assumption came from, so a report can never quietly
present an invented distribution as a measured one.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SPEC_VERSION = "2.0"


class Mode(str, Enum):
    SCHEMA_RULES = "schema_rules"
    LEARNED_TABLE = "learned_table"
    RELATIONAL_RULES = "relational_rules"


class Purpose(str, Enum):
    SOFTWARE_TESTING = "software_testing"
    TEACHING = "teaching"
    ANALYTICS = "analytics"
    ML_DEVELOPMENT = "ml_development"
    SCENARIO_SIMULATION = "scenario_simulation"


class SemanticRole(str, Enum):
    """What the platform is allowed to do with a column."""

    IDENTIFIER = "identifier"  # regenerate; never learn the original values
    LEARNED = "learned"  # a generator may model this
    RULE = "rule"  # sampled from an explicit declared rule
    DERIVED = "derived"  # computed from other columns after generation
    CONSTANT = "constant"  # single value throughout
    EMPTY = "empty"  # no observed values; dropped unless requested
    AGGREGATE = "aggregate"  # computed from related child records after generation


class ColumnType(str, Enum):
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CATEGORY = "category"
    STRING = "string"
    DATE = "date"
    TIMESTAMP = "timestamp"
    UUID = "uuid"


class Origin(str, Enum):
    """Where an assumption came from. Never inferred, always recorded."""

    USER = "user"  # a person stated it
    PROFILED = "profiled"  # measured from an approved source dataset
    PUBLIC_SOURCE = "public_source"  # taken from a cited public reference
    ASSISTANT_PROPOSED = "assistant_proposed"  # suggested by the LLM, not yet confirmed
    UNRESOLVED = "unresolved"  # known gap awaiting a decision


class Provenance(BaseModel):
    origin: Origin
    detail: str = ""
    reference: str | None = None
    confirmed: bool = False

    @property
    def is_assumption(self) -> bool:
        """True when this is a claim about the world that nobody has verified."""
        return self.origin in (Origin.ASSISTANT_PROPOSED, Origin.UNRESOLVED) or (
            self.origin == Origin.USER and not self.confirmed
        )


# --- derived-column expressions -------------------------------------------------
# A bounded vocabulary, evaluated by derive.py. Deliberately not Python or SQL: a
# specification arriving from an LLM or an HTTP client must not be able to smuggle in
# executable code. Unknown operators are rejected by the validator.

EXPR_OPS: dict[str, int | None] = {
    # arithmetic (n-ary where sensible)
    "add": None,
    "sub": 2,
    "mul": None,
    "div": 2,
    "round": 1,
    "floor": 1,
    "ceil": 1,
    "abs": 1,
    "clip": 3,
    "min": None,
    "max": None,
    # comparison
    "gt": 2,
    "ge": 2,
    "lt": 2,
    "le": 2,
    "eq": 2,
    "ne": 2,
    # logic
    "and": None,
    "or": None,
    "not": 1,
    "if_else": 3,
    # null handling
    "is_null": 1,
    "not_null": 1,
    "coalesce": None,
    # temporal
    "duration_hours": 2,  # (start, end) -> float hours
    "duration_seconds": 2,  # (start, end) -> float seconds
    "time_of_day": 1,  # timestamp -> float hours since local midnight
    "date_of": 1,  # timestamp -> date
    "day_of_week": 1,  # timestamp -> 0=Monday .. 6=Sunday
    "add_days": 2,
    "add_hours": 2,
    "add_seconds": 2,
}


class Expr(BaseModel):
    """One node of a derived-column expression.

    Exactly one of `op`, `col` or `const` is set. Kept as a single permissive model so
    a specification stays plain JSON that a form or an LLM can emit without ceremony.
    """

    op: str | None = None
    args: list["Expr"] = Field(default_factory=list)
    col: str | None = None
    const: Any = None
    # `time_of_day` and friends need to know the wall clock the business rule refers to
    tz_offset_hours: float = 0.0

    @model_validator(mode="after")
    def _exactly_one_form(self) -> "Expr":
        set_fields = sum(x is not None for x in (self.op, self.col, self.const))
        if set_fields != 1:
            raise ValueError(
                "each expression node needs exactly one of 'op', 'col' or 'const'"
            )
        if self.op is not None and self.op not in EXPR_OPS:
            raise ValueError(f"unknown operator '{self.op}'")
        return self

    def referenced_columns(self) -> set[str]:
        found = {self.col} if self.col else set()
        for arg in self.args:
            found |= arg.referenced_columns()
        return found


Expr.model_rebuild()


class RuleKind(str, Enum):
    """How a `rule` column is sampled when there are no source records."""

    FAKER = "faker"  # a Faker provider, e.g. "name", "company"
    SEQUENCE = "sequence"  # ORD-000001 ...
    UUID4 = "uuid4"
    CHOICE = "choice"  # weighted categorical draw
    INTEGER_RANGE = "integer_range"
    NUMBER_RANGE = "number_range"
    DATE_RANGE = "date_range"
    TIMESTAMP_RANGE = "timestamp_range"
    NORMAL = "normal"
    AR1 = "ar1"  # simple autoregressive series, for sensor-style scenarios


class Rule(BaseModel):
    kind: RuleKind
    provider: str | None = None  # Faker provider name
    prefix: str = ""
    start: Any = None
    end: Any = None
    values: list[Any] = Field(default_factory=list)
    weights: list[float] = Field(default_factory=list)
    mean: float | None = None
    stddev: float | None = None
    phi: float | None = None  # AR(1) coefficient
    decimals: int | None = None


class Column(BaseModel):
    name: str
    type: ColumnType
    role: SemanticRole = SemanticRole.LEARNED
    description: str = ""
    nullable: bool = False
    null_fraction: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[Any] | None = None
    constant_value: Any = None
    rule: Rule | None = None
    # `formula` computes this column from the generated output, after an engine runs.
    formula: Expr | None = None
    # `source_expression` computes it from the *source* data, before an engine fits —
    # feature engineering that has to survive in the specification so the same columns
    # can be rebuilt on a re-run. The two are deliberately separate: one describes how
    # a value is produced, the other how a training input is prepared.
    source_expression: Expr | None = None
    sensitive: bool = False  # metadata for policy handling, not a detection guarantee
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(origin=Origin.UNRESOLVED)
    )

    @model_validator(mode="after")
    def _role_requirements(self) -> "Column":
        if self.role == SemanticRole.DERIVED and self.formula is None:
            raise ValueError(f"derived column '{self.name}' needs a formula")
        if self.role == SemanticRole.RULE and self.rule is None:
            raise ValueError(f"rule column '{self.name}' needs a rule")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError(f"column '{self.name}' has minimum above maximum")
        return self


class ConstraintOperator(str, Enum):
    UNIQUE = "unique"
    LESS_OR_EQUAL = "less_or_equal"
    PRODUCT_EQUALS = "product_equals"  # a * b == c
    SUM_EQUALS = "sum_equals"  # a + b == c
    NOT_NULL = "not_null"
    IN_SET = "in_set"
    RANGE = "range"
    IMPLIES_NULL = "implies_null"  # when a is true, b must be null


CONSTRAINT_ARITY: dict[ConstraintOperator, int] = {
    ConstraintOperator.UNIQUE: 1,
    ConstraintOperator.LESS_OR_EQUAL: 2,
    ConstraintOperator.PRODUCT_EQUALS: 3,
    ConstraintOperator.SUM_EQUALS: 3,
    ConstraintOperator.NOT_NULL: 1,
    ConstraintOperator.IN_SET: 1,
    ConstraintOperator.RANGE: 1,
    ConstraintOperator.IMPLIES_NULL: 2,
}


class Constraint(BaseModel):
    operator: ConstraintOperator
    columns: list[str]
    values: list[Any] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    tolerance: float = 1e-9
    description: str = ""
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(origin=Origin.USER)
    )


class SourceKind(str, Enum):
    NONE = "none"
    UPLOADED_CSV = "uploaded_csv"
    PUBLIC_RECORDS = "public_records"


class Source(BaseModel):
    kind: SourceKind = SourceKind.NONE
    reference: str | None = None
    upload_id: str | None = None
    row_count: int | None = None
    sha256: str | None = None


class PrivacyIntent(BaseModel):
    """Recorded intent, never a guarantee.

    The benchmark in this repository measured a row-copying control reaching 0.291
    average precision against real data's 0.306 while reproducing training rows
    verbatim. High utility therefore demonstrably coexists with zero privacy, so no
    field here may be read as a release authorisation.
    """

    protected_entity: str | None = None  # e.g. "employee", not "row"
    mechanism: Literal["none", "differential_privacy"] = "none"
    epsilon: float | None = None
    release_claim_permitted: bool = False
    notes: str = ""


class Evaluation(BaseModel):
    checks: list[
        Literal["schema", "constraints", "fidelity", "predictive_utility", "cardinality"]
    ] = Field(default_factory=lambda: ["schema", "constraints"])
    target: str | None = None
    task: Literal["classification", "regression"] | None = None
    split: Literal["random", "group", "time"] = "random"
    split_column: str | None = None
    test_fraction: float = Field(default=0.25, gt=0, lt=0.5)


class Relationship(BaseModel):
    """A parent-child link. Used by relational modes; ignored by single-table engines."""

    parent_table: str
    parent_key: str
    child_table: str
    child_key: str
    cardinality: Literal["one_to_many", "one_to_one"] = "one_to_many"
    optional: bool = False
    null_fraction: float = Field(default=0.0, ge=0, lt=1)
    child_count_min: int | None = None
    child_count_max: int | None = None
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(origin=Origin.UNRESOLVED)
    )


class Table(BaseModel):
    name: str
    rows: int | None = None  # None means "derive from the relationship"
    primary_key: str | None = None
    unique_keys: list[list[str]] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    source: Source = Field(default_factory=Source)

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


class Aggregate(BaseModel):
    parent_table: str
    child_table: str
    child_key: str
    target_column: str
    operation: Literal["count", "sum", "mean", "min", "max"]
    source_column: str | None = None
    # count counts child rows; other operations ignore null input values.
    empty_value: float | None = None


class CrossTableConstraint(BaseModel):
    parent_table: str
    child_table: str
    child_key: str
    parent_column: str
    child_column: str
    operator: Literal["less_or_equal", "greater_or_equal"]
    missing: Literal["fail", "skip"] = "fail"


class SyntheticDataSpec(BaseModel):
    """The whole request. Single-table specs carry exactly one table."""

    spec_version: str = SPEC_VERSION
    name: str
    mode: Mode
    purpose: Purpose
    description: str = ""
    engine: str | None = None  # None lets the registry choose
    seed: int = 2026
    tables: list[Table] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    aggregates: list[Aggregate] = Field(default_factory=list)
    cross_table_constraints: list[CrossTableConstraint] = Field(default_factory=list)
    privacy: PrivacyIntent = Field(default_factory=PrivacyIntent)
    evaluation: Evaluation = Field(default_factory=Evaluation)

    def table(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name == name), None)

    @property
    def primary_table(self) -> Table:
        if not self.tables:
            raise ValueError("specification has no tables")
        return self.tables[0]

    @property
    def is_relational(self) -> bool:
        return len(self.tables) > 1 or bool(self.relationships)

    def open_assumptions(self) -> list[dict[str, str]]:
        """Every unconfirmed claim, for the report and the UI.

        A generated dataset is only as trustworthy as this list is short.
        """
        found: list[dict[str, str]] = []
        for table in self.tables:
            for column in table.columns:
                if column.provenance.is_assumption:
                    found.append(
                        {
                            "scope": f"{table.name}.{column.name}",
                            "origin": column.provenance.origin.value,
                            "detail": column.provenance.detail,
                        }
                    )
            for constraint in table.constraints:
                if constraint.provenance.is_assumption:
                    found.append(
                        {
                            "scope": f"{table.name}:{constraint.operator.value}",
                            "origin": constraint.provenance.origin.value,
                            "detail": constraint.provenance.detail,
                        }
                    )
        for rel in self.relationships:
            if rel.provenance.is_assumption:
                found.append(
                    {
                        "scope": f"{rel.parent_table}->{rel.child_table}",
                        "origin": rel.provenance.origin.value,
                        "detail": rel.provenance.detail,
                    }
                )
        return found
