"""Exploratory cross-domain synthesis benchmark. See ../04_benchmark_report.md.

All fitted transforms see training rows only. No privacy guarantee is claimed.
"""
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/synthetic-review-matplotlib")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import random
import time
import traceback
import warnings

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, norm, rankdata
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, roc_auc_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from copulas.multivariate import GaussianMultivariate
from copulas.univariate import GaussianUnivariate
from DataSynthesizer.DataDescriber import DataDescriber
from DataSynthesizer.DataGenerator import DataGenerator
from arfpy import arf

BASE = Path(__file__).resolve().parent
OUT = BASE / "results"
SEEDS = [11, 29, 47]
ENGINES = ["independent", "bootstrap_control", "copulas_rank_adapter", "datasynthesizer_bn", "arfpy"]

def datasets():
    bank = pd.read_csv(BASE / "data/bank.csv", sep=None, engine="python")
    bank = bank[["age", "job", "marital", "education", "default", "balance", "housing", "loan", "contact", "campaign", "previous", "poutcome", "y"]]
    bank["y"] = bank.y.map({"yes": 1, "no": 0})
    student = pd.read_csv(BASE / "data/student-mat.csv", sep=None, engine="python")
    student = student[["school", "sex", "age", "studytime", "failures", "schoolsup", "higher", "internet", "absences", "G1", "G2", "G3"]]
    wine = pd.read_csv(BASE / "data/winequality-red.csv", sep=None, engine="python")
    for name, df, target, task in [("bank", bank, "y", "classification"), ("student", student, "G3", "regression"), ("wine", wine, "quality", "regression")]:
        original = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        unique = len(df)
        if len(df) > 5000:
            df, _ = train_test_split(df, train_size=5000, random_state=2026, stratify=df[target] if task == "classification" else None)
            df = df.reset_index(drop=True)
        cats = df.select_dtypes(include=["object"]).columns.tolist()
        if task == "classification":
            cats.append(target)
        yield name, df, target, task, cats, {"original_rows": original, "unique_projected_rows": unique, "benchmark_rows": len(df), "columns": list(df), "categorical": cats}

def generate(engine, train, cats, seed, work):
    np.random.seed(seed)
    random.seed(seed)
    n = len(train)
    if engine == "independent":
        rng = np.random.default_rng(seed)
        return pd.DataFrame({c: rng.choice(train[c].to_numpy(), n) for c in train}), {}
    if engine == "bootstrap_control":
        return train.sample(n=n, replace=True, random_state=seed).reset_index(drop=True), {"warning": "Copies complete real training rows; diagnostic control only."}
    if engine == "copulas_rank_adapter":
        z, mappings = {}, {}
        rng = np.random.default_rng(seed)
        for c in train:
            if c in cats:
                values = sorted(train[c].unique().tolist(), key=str)
                p = train[c].value_counts(normalize=True).reindex(values).to_numpy()
                edges = np.r_[0, np.cumsum(p)]
                ix = pd.Categorical(train[c], categories=values).codes
                u = edges[ix] + rng.random(n) * p[ix]
                mappings[c] = (values, edges)
            else:
                u = (rankdata(train[c], method="average") - .5) / n
            z[c] = norm.ppf(np.clip(u, 1e-6, 1-1e-6))
        model = GaussianMultivariate(distribution=GaussianUnivariate, random_state=seed)
        model.fit(pd.DataFrame(z))
        sample = model.sample(n)
        for c in train:
            u = norm.cdf(sample[c])
            if c in cats:
                values, edges = mappings[c]
                sample[c] = np.asarray(values)[np.clip(np.searchsorted(edges, u, side="right") - 1, 0, len(values)-1)]
            else:
                sample[c] = np.quantile(train[c], u)
        return sample, {"adapter": "Randomized frequency intervals for nominal categories; empirical numeric inverse CDF. Category order is arbitrary."}
    if engine == "datasynthesizer_bn":
        train.to_csv(work / "train.csv", index=False)
        d = DataDescriber(category_threshold=10, histogram_bins=10)
        d.describe_dataset_in_correlated_attribute_mode(
            str(work / "train.csv"), k=1, epsilon=0,
            attribute_to_is_categorical={c: c in cats for c in train},
            attribute_to_is_candidate_key={c: False for c in train}, seed=seed)
        d.save_dataset_description_to_file(str(work / "description.json"))
        g = DataGenerator()
        g.generate_dataset_in_correlated_attribute_mode(n, str(work / "description.json"), seed=seed)
        return g.synthetic_dataset[train.columns], {"epsilon": 0, "meaning": "Library sentinel disabling privacy, NOT mathematical epsilon=0 DP", "k": 1, "histogram_bins": 10}
    if engine == "arfpy":
        x = train.copy()
        for c in cats:
            x[c] = x[c].astype("category")
        model = arf.arf(x, num_trees=30, max_iters=3, min_node_size=5, verbose=False, random_state=seed, n_jobs=1)
        model.forde()
        return model.forge(n), {"num_trees": 30, "max_iters": 3, "min_node_size": 5, "discriminator_oob_accuracy": model.acc}
    raise ValueError(engine)

def normalize_and_validate(raw, train, cats):
    x = raw.copy().reset_index(drop=True)
    invalid = np.zeros(len(x), dtype=bool)
    repaired = np.zeros(len(x), dtype=bool)
    for c in train:
        if c in cats:
            valid = x[c].isin(train[c].unique()).to_numpy()
            invalid |= ~valid
            # Never silently repair invalid categories.
            if not valid.all():
                raise ValueError(f"Unknown categories in {c}")
            x[c] = x[c].astype(train[c].dtype)
        else:
            values = pd.to_numeric(x[c], errors="coerce").to_numpy(dtype=float)
            bad = ~np.isfinite(values) | (values < train[c].min()-1e-9) | (values > train[c].max()+1e-9)
            invalid |= bad
            if not np.isfinite(values).all():
                raise ValueError(f"Nonfinite values in {c}")
            fixed = np.clip(values, train[c].min(), train[c].max())
            if pd.api.types.is_integer_dtype(train[c]):
                invalid |= np.abs(values - np.rint(values)) > 1e-9
                fixed = np.rint(fixed)
            repaired |= np.abs(values-fixed) > 1e-9
            x[c] = fixed.astype(train[c].dtype)
    return x, {"raw_invalid_row_fraction": float(invalid.mean()), "repaired_row_fraction": float(repaired.mean())}

def fidelity(syn, reference, cats):
    ks, tv = [], []
    for c in syn:
        if c in cats:
            p = syn[c].value_counts(normalize=True)
            q = reference[c].value_counts(normalize=True)
            labels = p.index.union(q.index)
            tv.append(.5 * np.abs(p.reindex(labels, fill_value=0)-q.reindex(labels, fill_value=0)).sum())
        else:
            ks.append(ks_2samp(syn[c], reference[c]).statistic)
    nums = [c for c in syn if c not in cats]
    a = syn[nums].corr(method="spearman").to_numpy()
    b = reference[nums].corr(method="spearman").to_numpy()
    ix = np.triu_indices(len(nums), 1)
    return {"mean_numeric_ks": float(np.mean(ks)), "mean_categorical_tv": float(np.mean(tv)) if tv else None,
            "numeric_spearman_mae": float(np.nanmean(np.abs(a[ix]-b[ix])))}

def exact_overlap(syn, train):
    # Full row match, for diagnostics only. This is not a privacy attack or guarantee.
    rows = set(map(tuple, train.itertuples(index=False, name=None)))
    return float(np.mean([r in rows for r in syn.itertuples(index=False, name=None)]))

def utility(fit, test, target, task, cats, seed):
    categorical = [c for c in cats if c != target]
    numeric = [c for c in fit if c != target and c not in categorical]
    result = {}
    for kind in ["linear", "forest"]:
        transform = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
            ("num", StandardScaler(), numeric)])
        if task == "classification":
            model = LogisticRegression(max_iter=2000, random_state=seed) if kind == "linear" else RandomForestClassifier(n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed)
        else:
            model = Ridge(alpha=1) if kind == "linear" else RandomForestRegressor(n_estimators=100, min_samples_leaf=3, n_jobs=1, random_state=seed)
        pipe = make_pipeline(transform, model)
        pipe.fit(fit.drop(columns=target), fit[target])
        if task == "classification":
            pred = pipe.predict_proba(test.drop(columns=target))[:, 1]
            result[kind + "_average_precision"] = average_precision_score(test[target], pred)
            result[kind + "_roc_auc"] = roc_auc_score(test[target], pred)
        else:
            pred = pipe.predict(test.drop(columns=target))
            result[kind + "_mae"] = mean_absolute_error(test[target], pred)
            result[kind + "_r2"] = r2_score(test[target], pred)
    return result

def main():
    OUT.mkdir(exist_ok=True)
    packages = ["numpy", "pandas", "scipy", "scikit-learn", "copulas", "DataSynthesizer", "arfpy", "Faker", "matplotlib"]
    env = {"started_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(), "platform": platform.platform(), "packages": {p: importlib.metadata.version(p) for p in packages}, "seeds": SEEDS, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / "environment.json").write_text(json.dumps(env, indent=2))
    rows, details, ds_info = [], [], {}
    for name, df, target, task, cats, info in datasets():
        ds_info[name] = info | {"target": target, "task": task}
        for seed in SEEDS:
            train, test = train_test_split(df, test_size=.25, random_state=seed, stratify=df[target] if task == "classification" else None)
            train, test = train.reset_index(drop=True), test.reset_index(drop=True)
            for engine in ["real_train_reference"] + ENGINES:
                record = {"dataset": name, "seed": seed, "engine": engine, "train_rows": len(train), "test_rows": len(test), "task": task}
                work = OUT / "runs" / f"{name}_{seed}_{engine}"
                work.mkdir(parents=True, exist_ok=True)
                (work / "split.json").write_text(json.dumps({"train_source_indices": train_test_split(df.index.to_numpy(), test_size=.25, random_state=seed, stratify=df[target] if task == "classification" else None)[0].tolist(), "test_source_indices": train_test_split(df.index.to_numpy(), test_size=.25, random_state=seed, stratify=df[target] if task == "classification" else None)[1].tolist()}))
                log = io.StringIO()
                try:
                    start = time.perf_counter()
                    with contextlib.redirect_stdout(log), warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        raw, settings = (train.copy(), {}) if engine == "real_train_reference" else generate(engine, train, cats, seed, work)
                        syn, validation = normalize_and_validate(raw, train, cats)
                        record["fit_sample_seconds"] = time.perf_counter() - start
                        record.update(validation)
                        record.update({"test_"+k: v for k, v in fidelity(syn, test, cats).items()})
                        record.update({"train_"+k: v for k, v in fidelity(syn, train, cats).items()})
                        record["exact_train_row_fraction"] = exact_overlap(syn, train)
                        record.update(utility(syn, test, target, task, cats, seed))
                        record["total_seconds"] = time.perf_counter() - start
                        record["status"] = "ok"
                        details.append({"dataset": name, "seed": seed, "engine": engine, "settings": settings,
                                        "warnings": sorted(set(str(w.message) for w in caught))})
                    syn.to_csv(work / "synthetic.csv", index=False)
                except Exception as exc:
                    record.update({"status": "failed", "error": repr(exc)})
                    log.write(traceback.format_exc())
                (work / "run.log").write_text(log.getvalue())
                rows.append(record)
                pd.DataFrame(rows).to_csv(OUT / "metrics.csv", index=False)
                (OUT / "run_details.json").write_text(json.dumps(details, indent=2, default=str))
                print(json.dumps(record), flush=True)
    (OUT / "dataset_summary.json").write_text(json.dumps(ds_info, indent=2))
    data = pd.DataFrame(rows)
    data[data.status == "ok"].groupby(["dataset", "engine"]).agg({c: ["mean", "std"] for c in data.select_dtypes(include="number") if c != "seed"}).to_csv(OUT / "summary.csv")
    env["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (OUT / "environment.json").write_text(json.dumps(env, indent=2))

if __name__ == "__main__":
    main()
