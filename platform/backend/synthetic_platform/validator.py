"""Semantic validation: everything JSON Schema cannot check.

Shape validation is Pydantic's job. This module answers the harder question of whether
a structurally valid specification actually *means* anything: do constraint columns
exist, can the chosen engine do what is being asked, is a derived column's formula
solvable, does a relational spec reference real parents.

Findings are returned rather than raised so the UI can show every problem at once
instead of one per round trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .derive import DerivationError, derivation_order
from .spec import (
    CONSTRAINT_ARITY,
    Column,
    ColumnType,
    ConstraintOperator,
    EXPR_OPS,
    Expr,
    Mode,
    SemanticRole,
    SourceKind,
    SyntheticDataSpec,
    Table,
)


class Severity(str, Enum):
    ERROR = "error"  # generation must not proceed
    WARNING = "warning"  # proceed, but the report must carry this


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    scope: str = ""

    def as_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "scope": self.scope,
        }


@dataclass
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [f.as_dict() for f in self.findings],
        }


NUMERIC_TYPES = {ColumnType.INTEGER, ColumnType.NUMBER}
TEMPORAL_TYPES = {ColumnType.DATE, ColumnType.TIMESTAMP}


def validate(spec: SyntheticDataSpec, engine_capabilities: dict | None = None) -> ValidationResult:
    result = ValidationResult()

    if not spec.tables:
        result.findings.append(
            Finding(Severity.ERROR, "no_tables", "The specification defines no tables.")
        )
        return result

    seen_tables: set[str] = set()
    for table in spec.tables:
        if table.name in seen_tables:
            result.findings.append(
                Finding(
                    Severity.ERROR,
                    "duplicate_table",
                    f"Table '{table.name}' is defined more than once.",
                    table.name,
                )
            )
        seen_tables.add(table.name)
        _validate_table(spec, table, result)

    _validate_relationships(spec, result)
    _validate_privacy(spec, result)
    _validate_evaluation(spec, result)

    if engine_capabilities is not None:
        _validate_capabilities(spec, engine_capabilities, result)

    return result


def _validate_table(spec: SyntheticDataSpec, table: Table, result: ValidationResult) -> None:
    scope = table.name

    if not table.columns:
        result.findings.append(
            Finding(Severity.ERROR, "no_columns", f"Table '{table.name}' has no columns.", scope)
        )
        return

    names = [c.name for c in table.columns]
    duplicates = {n for n in names if names.count(n) > 1}
    for name in sorted(duplicates):
        result.findings.append(
            Finding(Severity.ERROR, "duplicate_column", f"Column '{name}' is defined more than once.", scope)
        )

    known = set(names)

    if table.primary_key and table.primary_key not in known:
        result.findings.append(
            Finding(
                Severity.ERROR,
                "unknown_primary_key",
                f"Primary key '{table.primary_key}' is not a column of '{table.name}'.",
                scope,
            )
        )

    for column in table.columns:
        _validate_column(spec, table, column, known, result)

    # Derived columns must form a solvable dependency order.
    try:
        derivation_order(table)
    except DerivationError as exc:
        result.findings.append(Finding(Severity.ERROR, "derivation_cycle", str(exc), scope))

    for constraint in table.constraints:
        expected = CONSTRAINT_ARITY[constraint.operator]
        if len(constraint.columns) != expected:
            result.findings.append(
                Finding(
                    Severity.ERROR,
                    "constraint_arity",
                    f"Operator '{constraint.operator.value}' takes {expected} column(s), "
                    f"got {len(constraint.columns)}.",
                    scope,
                )
            )
        for name in constraint.columns:
            if name not in known:
                result.findings.append(
                    Finding(
                        Severity.ERROR,
                        "unknown_constraint_column",
                        f"Constraint '{constraint.operator.value}' references unknown column '{name}'.",
                        scope,
                    )
                )
        _validate_constraint_types(table, constraint, result, scope)

    if table.rows is not None and table.rows <= 0:
        result.findings.append(
            Finding(Severity.ERROR, "bad_row_count", f"Table '{table.name}' requests {table.rows} rows.", scope)
        )

    # A learned table with nothing to learn from cannot proceed.
    if spec.mode == Mode.LEARNED_TABLE:
        if table.source.kind == SourceKind.NONE:
            result.findings.append(
                Finding(
                    Severity.ERROR,
                    "missing_source",
                    f"Mode 'learned_table' needs an approved source for '{table.name}'.",
                    scope,
                )
            )
        learnable = [c for c in table.columns if c.role == SemanticRole.LEARNED]
        if not learnable:
            result.findings.append(
                Finding(
                    Severity.WARNING,
                    "nothing_to_learn",
                    f"Table '{table.name}' has no columns marked 'learned'; the learned "
                    "engine will have nothing to model.",
                    scope,
                )
            )

    if spec.mode == Mode.SCHEMA_RULES:
        for column in table.columns:
            if column.role == SemanticRole.LEARNED:
                result.findings.append(
                    Finding(
                        Severity.ERROR,
                        "learned_without_source",
                        f"Column '{column.name}' is marked 'learned' but mode "
                        "'schema_rules' has no source records to learn from.",
                        scope,
                    )
                )


def _validate_column(
    spec: SyntheticDataSpec,
    table: Table,
    column: Column,
    known: set[str],
    result: ValidationResult,
) -> None:
    scope = f"{table.name}.{column.name}"

    if column.role == SemanticRole.DERIVED:
        assert column.formula is not None
        _validate_expr(column.formula, known, column.name, result, scope)

    if column.role == SemanticRole.CONSTANT and column.constant_value is None:
        result.findings.append(
            Finding(Severity.WARNING, "constant_without_value",
                    f"Column '{column.name}' is constant but carries no value.", scope)
        )

    if column.role == SemanticRole.EMPTY:
        result.findings.append(
            Finding(Severity.WARNING, "empty_column",
                    f"Column '{column.name}' had no observed values and will be emitted as null.", scope)
        )

    if column.allowed_values is not None and len(column.allowed_values) == 0:
        result.findings.append(
            Finding(Severity.ERROR, "empty_allowed_values",
                    f"Column '{column.name}' declares an empty allowed-value set.", scope)
        )

    if column.null_fraction and not column.nullable:
        result.findings.append(
            Finding(Severity.ERROR, "null_fraction_conflict",
                    f"Column '{column.name}' is not nullable but requests a null fraction "
                    f"of {column.null_fraction}.", scope)
        )

    if not 0.0 <= column.null_fraction <= 1.0:
        result.findings.append(
            Finding(Severity.ERROR, "null_fraction_range",
                    f"Column '{column.name}' has a null fraction outside 0..1.", scope)
        )

    if column.sensitive and column.role == SemanticRole.LEARNED:
        result.findings.append(
            Finding(
                Severity.WARNING,
                "sensitive_learned",
                f"Column '{column.name}' is marked sensitive and will be learned from real "
                "records. Learned output is not anonymised.",
                scope,
            )
        )


def _validate_expr(
    expr: Expr, known: set[str], owner: str, result: ValidationResult, scope: str
) -> None:
    if expr.col is not None:
        if expr.col not in known:
            result.findings.append(
                Finding(Severity.ERROR, "formula_unknown_column",
                        f"Formula for '{owner}' references unknown column '{expr.col}'.", scope)
            )
        return
    if expr.const is not None:
        return

    arity = EXPR_OPS.get(expr.op or "")
    if expr.op not in EXPR_OPS:
        result.findings.append(
            Finding(Severity.ERROR, "unknown_operator",
                    f"Formula for '{owner}' uses unknown operator '{expr.op}'.", scope)
        )
        return
    if arity is not None and len(expr.args) != arity:
        result.findings.append(
            Finding(Severity.ERROR, "operator_arity",
                    f"Operator '{expr.op}' takes {arity} argument(s), got {len(expr.args)}.", scope)
        )
    if arity is None and not expr.args:
        result.findings.append(
            Finding(Severity.ERROR, "operator_arity",
                    f"Operator '{expr.op}' needs at least one argument.", scope)
        )
    for arg in expr.args:
        _validate_expr(arg, known, owner, result, scope)


def _validate_constraint_types(table: Table, constraint, result: ValidationResult, scope: str) -> None:
    columns = [table.column(n) for n in constraint.columns]
    if any(c is None for c in columns):
        return  # already reported as unknown

    op = constraint.operator
    if op in (ConstraintOperator.PRODUCT_EQUALS, ConstraintOperator.SUM_EQUALS):
        for column in columns:
            assert column is not None
            if column.type not in NUMERIC_TYPES:
                result.findings.append(
                    Finding(Severity.ERROR, "constraint_type",
                            f"Operator '{op.value}' needs numeric columns; '{column.name}' "
                            f"is {column.type.value}.", scope)
                )
    if op == ConstraintOperator.LESS_OR_EQUAL:
        kinds = {c.type for c in columns if c is not None}
        comparable = kinds <= NUMERIC_TYPES or kinds <= TEMPORAL_TYPES
        if not comparable:
            result.findings.append(
                Finding(Severity.ERROR, "constraint_type",
                        f"Operator 'less_or_equal' needs comparable columns of the same "
                        f"family; got {sorted(k.value for k in kinds)}.", scope)
            )
    if op == ConstraintOperator.RANGE and constraint.minimum is None and constraint.maximum is None:
        result.findings.append(
            Finding(Severity.ERROR, "range_without_bounds",
                    "A 'range' constraint needs a minimum, a maximum, or both.", scope)
        )
    if op == ConstraintOperator.IN_SET and not constraint.values:
        result.findings.append(
            Finding(Severity.ERROR, "in_set_without_values",
                    "An 'in_set' constraint needs at least one allowed value.", scope)
        )


def _validate_relationships(spec: SyntheticDataSpec, result: ValidationResult) -> None:
    table_names = {t.name for t in spec.tables}

    for rel in spec.relationships:
        scope = f"{rel.parent_table}->{rel.child_table}"
        parent, child = spec.table(rel.parent_table), spec.table(rel.child_table)

        if parent is None:
            result.findings.append(
                Finding(Severity.ERROR, "unknown_parent_table",
                        f"Relationship references unknown parent table '{rel.parent_table}'.", scope)
            )
        if child is None:
            result.findings.append(
                Finding(Severity.ERROR, "unknown_child_table",
                        f"Relationship references unknown child table '{rel.child_table}'.", scope)
            )
        if parent is None or child is None:
            continue

        if parent.column(rel.parent_key) is None:
            result.findings.append(
                Finding(Severity.ERROR, "unknown_parent_key",
                        f"Parent key '{rel.parent_key}' is not a column of '{parent.name}'.", scope)
            )
        if child.column(rel.child_key) is None:
            result.findings.append(
                Finding(Severity.ERROR, "unknown_child_key",
                        f"Foreign key '{rel.child_key}' is not a column of '{child.name}'.", scope)
            )
        if parent.primary_key and parent.primary_key != rel.parent_key:
            result.findings.append(
                Finding(Severity.WARNING, "parent_key_not_primary",
                        f"Relationship uses '{rel.parent_key}' but '{parent.name}' declares "
                        f"primary key '{parent.primary_key}'.", scope)
            )
        if (
            rel.child_count_min is not None
            and rel.child_count_max is not None
            and rel.child_count_min > rel.child_count_max
        ):
            result.findings.append(
                Finding(Severity.ERROR, "bad_cardinality",
                        "Minimum child count exceeds the maximum.", scope)
            )

    if _has_cycle(spec):
        result.findings.append(
            Finding(Severity.ERROR, "relationship_cycle",
                    "The relationship graph contains a cycle; generation order is undefined.")
        )

    if spec.is_relational and spec.mode not in (Mode.RELATIONAL_RULES,):
        result.findings.append(
            Finding(Severity.ERROR, "relational_mode_required",
                    f"The specification defines relationships but mode is '{spec.mode.value}'. "
                    "Use 'relational_rules'.")
        )
    _ = table_names


def _has_cycle(spec: SyntheticDataSpec) -> bool:
    edges: dict[str, list[str]] = {t.name: [] for t in spec.tables}
    for rel in spec.relationships:
        if rel.parent_table in edges and rel.child_table in edges:
            edges[rel.parent_table].append(rel.child_table)

    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(edges, WHITE)

    def visit(node: str) -> bool:
        colour[node] = GREY
        for nxt in edges.get(node, []):
            if colour[nxt] == GREY:
                return True
            if colour[nxt] == WHITE and visit(nxt):
                return True
        colour[node] = BLACK
        return False

    return any(colour[n] == WHITE and visit(n) for n in list(edges))


def _validate_privacy(spec: SyntheticDataSpec, result: ValidationResult) -> None:
    privacy = spec.privacy

    if privacy.release_claim_permitted:
        result.findings.append(
            Finding(
                Severity.ERROR,
                "unsupported_release_claim",
                "No engine in this platform provides a formal privacy guarantee, so a "
                "release claim cannot be permitted. The benchmark's row-copying control "
                "reached near-real utility while reproducing training rows verbatim.",
            )
        )

    if privacy.mechanism == "differential_privacy":
        result.findings.append(
            Finding(Severity.ERROR, "dp_not_implemented",
                    "Differential privacy is not implemented. No DP engine is registered.")
        )

    learning_from_records = spec.mode == Mode.LEARNED_TABLE
    if learning_from_records and not privacy.protected_entity:
        result.findings.append(
            Finding(
                Severity.WARNING,
                "no_protected_entity",
                "Learning from real records without a declared protected entity. For "
                "employee data the protected unit is usually the employee, not the row.",
            )
        )


def _validate_evaluation(spec: SyntheticDataSpec, result: ValidationResult) -> None:
    evaluation = spec.evaluation
    table = spec.primary_table
    known = {c.name for c in table.columns}

    if "predictive_utility" in evaluation.checks:
        if not evaluation.target:
            result.findings.append(
                Finding(Severity.ERROR, "utility_without_target",
                        "Evaluation requests predictive utility but names no target column.")
            )
        elif evaluation.target not in known:
            result.findings.append(
                Finding(Severity.ERROR, "unknown_target",
                        f"Evaluation target '{evaluation.target}' is not a column of "
                        f"'{table.name}'.")
            )
        if spec.mode == Mode.SCHEMA_RULES:
            result.findings.append(
                Finding(
                    Severity.WARNING,
                    "utility_on_invented_data",
                    "Predictive utility on schema-only data measures the rules that were "
                    "written, not a fact about any real population.",
                )
            )

    if "fidelity" in evaluation.checks and spec.mode == Mode.SCHEMA_RULES:
        result.findings.append(
            Finding(Severity.ERROR, "fidelity_without_source",
                    "Fidelity compares against source records; mode 'schema_rules' has none.")
        )

    if "cardinality" in evaluation.checks and not spec.is_relational:
        result.findings.append(
            Finding(Severity.WARNING, "cardinality_without_relationships",
                    "Cardinality evaluation needs relationships; none are defined.")
        )


def _validate_capabilities(spec: SyntheticDataSpec, caps: dict, result: ValidationResult) -> None:
    """Stop a single-table engine from silently accepting a relational request."""
    if spec.is_relational and not caps.get("multi_table", False):
        result.findings.append(
            Finding(
                Severity.ERROR,
                "engine_lacks_multi_table",
                f"Engine '{caps.get('name', '?')}' does not support relational generation.",
            )
        )
    if spec.mode == Mode.LEARNED_TABLE and not caps.get("learns_from_records", False):
        result.findings.append(
            Finding(Severity.ERROR, "engine_cannot_learn",
                    f"Engine '{caps.get('name', '?')}' cannot learn from source records.")
        )
    if spec.mode == Mode.SCHEMA_RULES and not caps.get("schema_only", False):
        result.findings.append(
            Finding(Severity.ERROR, "engine_needs_records",
                    f"Engine '{caps.get('name', '?')}' requires source records.")
        )
    supported = set(caps.get("constraints", []))
    if supported:
        for table in spec.tables:
            for constraint in table.constraints:
                if constraint.operator.value not in supported:
                    result.findings.append(
                        Finding(
                            Severity.ERROR,
                            "unsupported_constraint",
                            f"Engine '{caps.get('name', '?')}' does not support constraint "
                            f"'{constraint.operator.value}'.",
                            table.name,
                        )
                    )

    # A type an engine accepts can still be unusable at scale. A categorical model over
    # thousands of levels is the same failure as an unsupported type, just slower to
    # arrive, so the ceiling is checked in the same place.
    ceiling = caps.get("max_category_levels")
    if ceiling:
        categorical = {ColumnType.CATEGORY, ColumnType.STRING}
        for table in spec.tables:
            for column in table.columns:
                if column.role not in {SemanticRole.LEARNED, SemanticRole.RULE}:
                    continue
                if column.type not in categorical or column.allowed_values is None:
                    continue
                levels = len(column.allowed_values)
                if levels > ceiling:
                    result.findings.append(
                        Finding(
                            Severity.ERROR,
                            "too_many_category_levels",
                            f"Column '{column.name}' has {levels:,} distinct values, but "
                            f"engine '{caps.get('name', '?')}' handles at most "
                            f"{ceiling:,} as a category. Group the values, mark the "
                            "column an identifier so it is regenerated, or derive a "
                            "lower-cardinality feature from it.",
                            f"{table.name}.{column.name}",
                        )
                    )

    # Only columns an engine actually models need to be a type it supports; the rest
    # are filled by the platform. Without this check a tree-based engine is handed raw
    # timestamps and either fails deep inside its own fit or runs for a very long time
    # before doing so.
    supported_types = set(caps.get("supported_types", []))
    if supported_types:
        modelled_roles = {SemanticRole.LEARNED, SemanticRole.RULE}
        for table in spec.tables:
            for column in table.columns:
                if column.role not in modelled_roles:
                    continue
                if column.type.value in supported_types:
                    continue
                result.findings.append(
                    Finding(
                        Severity.ERROR,
                        "unsupported_column_type",
                        f"Engine '{caps.get('name', '?')}' cannot model a "
                        f"'{column.type.value}' column, so '{column.name}' has to be "
                        "handled another way — derive it from a supported column, give "
                        "it an explicit rule, or choose a different engine.",
                        f"{table.name}.{column.name}",
                    )
                )
