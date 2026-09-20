"""Build human-readable tables and a shareable chart from measured results."""
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/synthetic-review-matplotlib")
import json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks/results"
df = pd.read_csv(RESULTS / "metrics.csv")
assert len(df) == 54 and df.status.eq("ok").all()
engines = ["real_train_reference", "bootstrap_control", "independent", "copulas_rank_adapter", "datasynthesizer_bn", "arfpy"]
names = {"real_train_reference": "Real training reference", "bootstrap_control": "Row-copying control", "independent": "Independent sampling", "copulas_rank_adapter": "Copulas + rank adapter", "datasynthesizer_bn": "DataSynthesizer BN", "arfpy": "arfpy"}

def fmt(values):
    return f"{values.mean():.3f} ± {values.std(ddof=1):.3f}"

rows = []
for engine in engines:
    row = [names[engine]]
    for dataset, metric in [("bank", "forest_average_precision"), ("student", "forest_mae"), ("wine", "forest_mae")]:
        row.append(fmt(df[(df.engine == engine) & (df.dataset == dataset)][metric]))
    rows.append("| " + " | ".join(row) + " |")
table = "| Method | Banking AP ↑ | Student grade MAE ↓ | Wine quality MAE ↓ |\n|---|---:|---:|---:|\n" + "\n".join(rows)

detail = "| Dataset | Method | Numeric KS ↓ | Categorical TV ↓ | Numeric correlation MAE ↓ | Fit/sample seconds | Exact training-row match | Rows repaired |\n|---|---|---:|---:|---:|---:|---:|---:|\n"
for dataset in ["bank", "student", "wine"]:
    for engine in engines:
        a = df[(df.dataset == dataset) & (df.engine == engine)]
        tv = a.test_mean_categorical_tv.mean()
        detail += f"| {dataset} | {names[engine]} | {a.test_mean_numeric_ks.mean():.3f} | {tv:.3f} | {a.test_numeric_spearman_mae.mean():.3f} | {a.fit_sample_seconds.mean():.3f} | {a.exact_train_row_fraction.mean():.4f} | {a.repaired_row_fraction.mean():.3f} |\n".replace("nan", "N/A")

linear = "| Method | Banking logistic AP ↑ | Student ridge MAE ↓ | Wine ridge MAE ↓ |\n|---|---:|---:|---:|\n"
for engine in engines:
    row = [names[engine]]
    for dataset, metric in [("bank", "linear_average_precision"), ("student", "linear_mae"), ("wine", "linear_mae")]:
        row.append(fmt(df[(df.engine == engine) & (df.dataset == dataset)][metric]))
    linear += "| " + " | ".join(row) + " |\n"

report = """# Executed benchmark report

This is a CPU-based, exploratory comparison, executed on 20 September 2026. It is not a universal tool ranking, privacy certification or final production acceptance test.

## What actually ran

Three datasets × three split/generation seeds × six methods = **54 completed runs**. Each run evaluated both a forest and a linear downstream model, giving 108 predictor fits. Of the six methods, three use installed external synthesis libraries, one is an independent-column baseline, one copies real rows as a diagnostic, and one trains directly on real rows as a reference. All 54 succeeded.

Versions: Python 3.12.3; NumPy 2.3.5; pandas 2.3.3; SciPy 1.16.3; scikit-learn 1.8.0; Copulas 0.14.1; DataSynthesizer 0.1.13; arfpy 0.1.1. The complete capture is in [environment.json](benchmarks/results/environment.json).

## Inputs and tasks

| Domain / source | Raw → deduplicated projected rows | Columns including target | Task |
|---|---:|---:|---|
| [UCI Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing), bank.csv | 4,521 → 4,518 | 13 | Predict deposit subscription; exclude call duration |
| [UCI Student Performance](https://archive.ics.uci.edu/dataset/320/student+performance), mathematics | 395 → 392 | 12 | Predict final grade using selected fields including earlier grades G1/G2 |
| [UCI Wine Quality](https://archive.ics.uci.edu/dataset/186/wine+quality), red wine | 1,599 → 1,359 | 12 | Predict quality score from physicochemical features |

UCI lists these datasets as CC BY 4.0. See [attribution](benchmarks/data/README.md) and [primary file hashes](benchmarks/data/manifest.json). The final benchmark used original UCI files, not the temporarily explored mirrors. Feature lists are in [dataset_summary.json](benchmarks/results/dataset_summary.json).

We remove exact duplicates of the selected columns before splitting to reduce duplicate leakage. This changes the benchmark distribution; published results on the full datasets are not directly comparable. Bank data may contain repeated clients without identifiers; record-level splitting does not establish person-level independence. Student prediction is a **later-year prediction task**, not an early-intervention model. No causal or deployment claims follow from it.

## Protocol

Seeds 11, 29 and 47 each produce a 75% training / 25% held-out split. Banking is stratified by label. The same split is used for every method at a seed. Generators fit the joint table including the target and generate exactly as many rows as the training partition. Encoders, marginal estimates and bounds use training rows only. Downstream preprocessing is fitted independently on the actual real or synthetic training input.

No hyperparameter search used the held-out partitions. Nevertheless this is exploratory model comparison; a newly locked evaluation or new dataset is needed before final acceptance. Three-seed standard deviations describe observed variability, **not confidence intervals** or a significance test. Split and generator seeds change together, so these sources of variability are not isolated.

Methods:

- **Independent:** sample each column independently from its empirical training values.
- **Copy control:** bootstrap complete training rows. Useful to expose metric limitations; never a privacy mechanism.
- **Copulas adapter:** randomized category-frequency intervals and empirical numeric ranks → GaussianMultivariate with Gaussian marginals → inverse empirical transforms. Nominal category ordering is arbitrary. Results describe this adapter, not stock SDV or an optimized copula synthesizer.
- **DataSynthesizer:** correlated mode, one parent, 10 histogram bins, explicit categorical/key flags, epsilon=0. In this library **zero disables noise**; it does not mean a mathematical zero-epsilon privacy guarantee.
- **arfpy:** 30 trees, at most three adversarial iterations, minimum leaf size five, density estimation and generation; one worker.
- **Real reference:** train downstream predictors on real training data.

Downstream predictors: random forest with 100 trees and minimum leaf size three, plus logistic regression (bank) or ridge regression (student/wine). We report average precision (AP) for the imbalanced binary task and mean absolute error (MAE) for regression. ROC AUC and R² are also saved. Settings are fixed, not independently optimized for each method.

## Predictive utility: forest model

Mean ± sample standard deviation over three runs. Higher AP is better; lower MAE is better. MAE uses each dataset's native outcome units and cannot be compared across datasets.

TABLE

![Measured utility across three domains](benchmarks/results/utility_comparison.png)

## Predictive utility: linear model sensitivity check

LINEAR

## Fidelity, runtime and copying diagnostics

Values are means across seeds. KS and TV compare individual synthetic columns with the held-out set; correlation error covers numeric Spearman correlations only. Categorical/continuous dependence and higher-order interactions are not fully measured here. N/A means no categorical columns, not a perfect score. Timing includes fitting, sampling and normalization, excludes installation/download and downstream predictor fitting. Real/copy timings are not model-training benchmarks.

DETAIL

Raw generated numeric values are clipped to the training range and integer columns are rounded. Unknown categories or nonfinite output would fail the run. Repair fractions disclose this work: high fractions can arise when one integer field is returned continuously, not necessarily from severe semantic errors. They demonstrate that the wrapper, not the native generator alone, enforces these types. All reported fidelity and utility metrics describe the repaired output. These checks do not cover arbitrary cross-column business rules.

Exact training-row matches are **diagnostics, not privacy scores**. Absence of matches does not prevent membership or attribute inference; a coincidental match on common attributes need not establish memorization. The copying control is 100% matches by construction.

## Findings supported by these runs

1. Dependency modeling matters. All three learned adapters substantially improve the student task over independent sampling. Matching individual-column distributions is insufficient.
2. There is no universal winner. ARF leads the tested generators on banking forest AP; the copula adapter leads on student MAE; ARF and the copula adapter are close on wine with substantial seed overlap.
3. DataSynthesizer's selected equal-width, 10-bin setup has poor banking numeric KS. This is evidence about this configuration, not proof that Bayesian methods are inferior.
4. High utility alone cannot establish privacy: the copying control performs relatively well while reproducing real training rows.
5. ARF is a defensible first permissively licensed learned adapter, but it requires explicit normalization and is not the strongest tested approach on every task. Copulas is a useful comparator with a BSL license constraint.

## Schema-only demonstrations

The separate [rule example script](benchmarks/rule_examples.py) generated 1,000 retail orders, 1,000 education records and 1,000 sequential sensor readings. All eight explicit checks passed: unique identifiers where specified, monetary arithmetic, shipment ordering, credit/fraction bounds and sensor time/range bounds. The sensor scenario uses an explicitly invented AR(1)-style rule; it is not a learned time-series benchmark. Faker supplies retail display names; relationships come from our code.

These demonstrate structure and assumptions, not population realism. [Measurements](benchmarks/results/rule_examples/metrics.json) and CSV outputs are included.

## What remains unmeasured

- Differential privacy, privacy attacks, membership inference, individual-level disclosure and privacy–utility curves.
- Neural generators, learned time series, relational synthesis and aggregation-only inference.
- Missing-value preservation, rare-category stress tests, conditional sampling, very wide/large data and rigorous fairness assessment.
- Query workloads, confidence-interval validity, causal behavior, augmented-real-data performance and out-of-distribution generalization.
- LLM correctness, usability, costs and institutional deployment.
- Peak memory, GPU performance and process-isolated latency; the timing comparison is exploratory.

The selected public datasets, feature subsets, small sample sizes, three seeds and fixed tuning budget limit generalization. No result establishes usefulness for an unseen institution or every domain.

## Reproduction

From the project root, create an isolated environment, install [requirements.txt](benchmarks/requirements.txt), and run:

```bash
python "litreatrue reveiw/benchmarks/run_benchmark.py"
python "litreatrue reveiw/benchmarks/rule_examples.py"
python "litreatrue reveiw/benchmarks/build_report.py"
python "litreatrue reveiw/benchmarks/verify_artifacts.py"
```

The archived CSV inputs are sufficient; network access is unnecessary for a rerun after installation. Results overwrite the experiment outputs. Preserve a copy if retaining the original timings matters. Floating point/library/platform differences can affect exact reproduction.

Raw outputs: [metrics.csv](benchmarks/results/metrics.csv), [summary.csv](benchmarks/results/summary.csv), [run details](benchmarks/results/run_details.json), [execution log](benchmarks/results/execution.log), and per-run CSVs/logs/split indices under `benchmarks/results/runs/`.
""".replace("TABLE", table).replace("LINEAR", linear).replace("DETAIL", detail)
(ROOT / "04_benchmark_report.md").write_text(report)

fig, axes = plt.subplots(1, 3, figsize=(14, 5.6), constrained_layout=True)
colors = ["#64748b", "#d97706", "#94a3b8", "#2563eb", "#7c3aed", "#059669"]
for ax, dataset, metric, title in zip(axes, ["bank", "student", "wine"], ["forest_average_precision", "forest_mae", "forest_mae"], ["Banking: AP (higher is better)", "Education: MAE (lower is better)", "Product quality: MAE (lower is better)"]):
    groups = [df[(df.dataset == dataset) & (df.engine == e)][metric] for e in engines]
    ax.barh([names[e] for e in engines], [x.mean() for x in groups], xerr=[x.std(ddof=1) for x in groups], color=colors, capsize=3)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=11)
    ax.grid(axis="x", alpha=.2)
    ax.set_axisbelow(True)
fig.suptitle("Exploratory synthetic-data benchmark • 3 seeds • forest downstream model\nError bars are standard deviations; copying control is not privacy-preserving", fontsize=13)
fig.savefig(RESULTS / "utility_comparison.png", dpi=160)
fig.savefig(RESULTS / "utility_comparison.svg")
print("Wrote benchmark report and PNG/SVG chart")
