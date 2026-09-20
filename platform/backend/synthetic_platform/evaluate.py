"""Evaluation, owned by the platform rather than by any engine.

An engine may report diagnostics about itself, but it never decides whether its own
output was good. Everything here runs on the finished table.

Three kinds of check, deliberately kept separate because they answer different
questions and are not interchangeable:

  constraints  — did the declared hard rules survive? A pass/fail fact.
  fidelity     — do the distributions resemble the source? Necessary, not sufficient.
  utility      — does a model trained on this data still work on real held-out rows?

The benchmark behind this platform is the reason for keeping them apart: independent
column sampling scored a near-perfect 0.025 KS on banking marginals while collapsing
downstream utility from 0.306 to 0.141. Fidelity alone would have called that a
success.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .spec import ColumnType, Constraint, ConstraintOperator, SemanticRole, Table


# --- constraints ----------------------------------------------------------------


def check_constraints(frame: pd.DataFrame, table: Table) -> list[dict]:
    """Evaluate every declared constraint. These are hard rules, not scores."""
    results: list[dict] = []
    for constraint in table.constraints:
        try:
            passed, failures, detail = _check_one(frame, constraint)
        except KeyError as exc:
            results.append(
                {
                    "operator": constraint.operator.value,
                    "columns": constraint.columns,
                    "passed": False,
                    "failing_rows": len(frame),
                    "detail": f"column not present in output: {exc}",
                }
            )
            continue
        results.append(
            {
                "operator": constraint.operator.value,
                "columns": constraint.columns,
                "passed": passed,
                "failing_rows": failures,
                "detail": detail,
                "description": constraint.description,
            }
        )
    return results


def _check_one(frame: pd.DataFrame, constraint: Constraint) -> tuple[bool, int, str]:
    op = constraint.operator
    cols = constraint.columns

    if op == ConstraintOperator.UNIQUE:
        series = frame[cols[0]]
        duplicated = int(series.duplicated().sum())
        return duplicated == 0, duplicated, f"{series.nunique()} distinct of {len(series)}"

    if op == ConstraintOperator.NOT_NULL:
        missing = int(frame[cols[0]].isna().sum())
        return missing == 0, missing, f"{missing} nulls"

    if op == ConstraintOperator.LESS_OR_EQUAL:
        left, right = frame[cols[0]], frame[cols[1]]
        if not pd.api.types.is_numeric_dtype(left):
            left = pd.to_datetime(left, format="mixed", utc=True, errors="coerce")
            right = pd.to_datetime(right, format="mixed", utc=True, errors="coerce")
        comparable = left.notna() & right.notna()
        bad = int((left[comparable] > right[comparable]).sum())
        return bad == 0, bad, f"{cols[0]} <= {cols[1]}"

    if op == ConstraintOperator.PRODUCT_EQUALS:
        a, b, c = (pd.to_numeric(frame[x], errors="coerce") for x in cols)
        bad = int((np.abs(a * b - c) > constraint.tolerance).sum())
        return bad == 0, bad, f"{cols[0]} * {cols[1]} == {cols[2]}"

    if op == ConstraintOperator.SUM_EQUALS:
        a, b, c = (pd.to_numeric(frame[x], errors="coerce") for x in cols)
        bad = int((np.abs(a + b - c) > constraint.tolerance).sum())
        return bad == 0, bad, f"{cols[0]} + {cols[1]} == {cols[2]}"

    if op == ConstraintOperator.IN_SET:
        allowed = set(constraint.values)
        series = frame[cols[0]].dropna()
        bad = int((~series.isin(allowed)).sum())
        return bad == 0, bad, f"{len(allowed)} allowed values"

    if op == ConstraintOperator.RANGE:
        series = pd.to_numeric(frame[cols[0]], errors="coerce")
        bad_mask = pd.Series(False, index=series.index)
        if constraint.minimum is not None:
            bad_mask |= series < constraint.minimum
        if constraint.maximum is not None:
            bad_mask |= series > constraint.maximum
        bad = int(bad_mask.sum())
        return bad == 0, bad, f"[{constraint.minimum}, {constraint.maximum}]"

    if op == ConstraintOperator.IMPLIES_NULL:
        flag = frame[cols[0]].astype(bool)
        target = frame[cols[1]]
        bad = int((flag & target.notna()).sum())
        return bad == 0, bad, f"when {cols[0]} then {cols[1]} is null"

    raise ValueError(f"constraint '{op}' is not implemented")


# --- fidelity -------------------------------------------------------------------


def fidelity(synthetic: pd.DataFrame, reference: pd.DataFrame, table: Table) -> dict:
    """Compare distributions. Necessary but never sufficient evidence of quality."""
    numeric_ks: dict[str, float] = {}
    categorical_tv: dict[str, float] = {}

    modelled = [
        c for c in table.columns
        if c.role in (SemanticRole.LEARNED, SemanticRole.RULE, SemanticRole.DERIVED)
    ]

    for column in modelled:
        name = column.name
        if name not in synthetic.columns or name not in reference.columns:
            continue
        if column.type in (ColumnType.INTEGER, ColumnType.NUMBER):
            left = pd.to_numeric(synthetic[name], errors="coerce").dropna()
            right = pd.to_numeric(reference[name], errors="coerce").dropna()
            if len(left) and len(right):
                numeric_ks[name] = float(ks_2samp(left, right).statistic)
        elif column.type in (ColumnType.CATEGORY, ColumnType.BOOLEAN):
            p = synthetic[name].value_counts(normalize=True)
            q = reference[name].value_counts(normalize=True)
            labels = p.index.union(q.index)
            categorical_tv[name] = float(
                0.5 * np.abs(p.reindex(labels, fill_value=0) - q.reindex(labels, fill_value=0)).sum()
            )

    correlation_mae = _correlation_error(synthetic, reference, table)

    return {
        "numeric_ks": numeric_ks,
        "categorical_tv": categorical_tv,
        "mean_numeric_ks": float(np.mean(list(numeric_ks.values()))) if numeric_ks else None,
        "mean_categorical_tv": float(np.mean(list(categorical_tv.values()))) if categorical_tv else None,
        "numeric_correlation_mae": correlation_mae,
        "exact_row_match_fraction": _exact_overlap(synthetic, reference, table),
        "interpretation": (
            "KS and total-variation compare one column at a time; correlation error covers "
            "numeric pairs only. Matching marginals does not establish that relationships "
            "between columns survived."
        ),
    }


def _correlation_error(synthetic: pd.DataFrame, reference: pd.DataFrame, table: Table) -> float | None:
    numeric = [
        c.name
        for c in table.columns
        if c.type in (ColumnType.INTEGER, ColumnType.NUMBER)
        and c.name in synthetic.columns
        and c.name in reference.columns
        and c.role != SemanticRole.IDENTIFIER
    ]
    if len(numeric) < 2:
        return None
    a = synthetic[numeric].apply(pd.to_numeric, errors="coerce").corr(method="spearman").to_numpy()
    b = reference[numeric].apply(pd.to_numeric, errors="coerce").corr(method="spearman").to_numpy()
    idx = np.triu_indices(len(numeric), 1)
    diff = np.abs(a[idx] - b[idx])
    return float(np.nanmean(diff)) if diff.size else None


def _exact_overlap(synthetic: pd.DataFrame, reference: pd.DataFrame, table: Table) -> float:
    """Fraction of synthetic rows reproducing a source row exactly.

    A diagnostic, never a privacy score. Identifiers are excluded because they are
    regenerated by design and would mask a real copy.
    """
    comparable = [
        c.name
        for c in table.columns
        if c.role != SemanticRole.IDENTIFIER
        and c.name in synthetic.columns
        and c.name in reference.columns
    ]
    if not comparable:
        return 0.0
    source_rows = set(map(tuple, reference[comparable].astype(str).itertuples(index=False, name=None)))
    matches = [
        row in source_rows
        for row in synthetic[comparable].astype(str).itertuples(index=False, name=None)
    ]
    return float(np.mean(matches)) if matches else 0.0


# --- predictive utility ----------------------------------------------------------


def predictive_utility(
    synthetic: pd.DataFrame,
    reference: pd.DataFrame,
    table: Table,
    target: str,
    task: str,
    seed: int = 2026,
) -> dict:
    """Train on synthetic, test on held-out real rows, and compare against real training.

    Reporting the synthetic score alone would be meaningless: the number only means
    something next to what the same model achieves on real data, and next to what the
    independent-sampling floor achieves.
    """
    features = [
        c.name
        for c in table.columns
        if c.name != target
        and c.role not in (SemanticRole.IDENTIFIER, SemanticRole.EMPTY, SemanticRole.CONSTANT)
        and c.name in synthetic.columns
        and c.name in reference.columns
    ]
    if not features:
        return {"error": "no usable feature columns"}
    if target not in synthetic.columns or target not in reference.columns:
        return {"error": f"target '{target}' missing from one of the frames"}

    real_train, real_test = train_test_split(
        reference.dropna(subset=[target]),
        test_size=0.25,
        random_state=seed,
        stratify=reference.dropna(subset=[target])[target] if task == "classification" else None,
    )

    categorical = [
        c.name
        for c in table.columns
        if c.name in features and c.type in (ColumnType.CATEGORY, ColumnType.STRING, ColumnType.BOOLEAN)
    ]
    numeric = [f for f in features if f not in categorical]

    def score(train_frame: pd.DataFrame) -> dict:
        train_frame = train_frame.dropna(subset=[target])
        if train_frame.empty:
            return {"error": "no training rows"}
        transform = ColumnTransformer(
            [
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
                ("num", StandardScaler(), numeric),
            ]
        )
        if task == "classification":
            model = RandomForestClassifier(
                n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed
            )
        else:
            model = RandomForestRegressor(
                n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed
            )
        pipe = make_pipeline(transform, model)
        pipe.fit(train_frame[features], train_frame[target])

        if task == "classification":
            proba = pipe.predict_proba(real_test[features])
            if proba.shape[1] < 2:
                return {"error": "training data contained a single class"}
            pred = proba[:, 1]
            return {
                "average_precision": float(average_precision_score(real_test[target], pred)),
                "roc_auc": float(roc_auc_score(real_test[target], pred)),
            }
        pred = pipe.predict(real_test[features])
        return {
            "mae": float(mean_absolute_error(real_test[target], pred)),
            "r2": float(r2_score(real_test[target], pred)),
        }

    rng = np.random.default_rng(seed)
    independent = pd.DataFrame(
        {c: rng.choice(real_train[c].to_numpy(), len(real_train)) for c in real_train.columns}
    )

    return {
        "target": target,
        "task": task,
        "metric": "average_precision" if task == "classification" else "mae",
        "better": "higher" if task == "classification" else "lower",
        "test_rows": int(len(real_test)),
        "trained_on_synthetic": score(synthetic),
        "trained_on_real": score(real_train),
        "trained_on_independent_baseline": score(independent),
        "interpretation": (
            "Synthetic data is useful for this task to the extent its score approaches the "
            "real-data score and clearly beats the independent baseline. A score close to "
            "real does not indicate privacy."
        ),
    }
