# Executed benchmark report

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

| Method | Banking AP ↑ | Student grade MAE ↓ | Wine quality MAE ↓ |
|---|---:|---:|---:|
| Real training reference | 0.306 ± 0.015 | 0.994 ± 0.082 | 0.482 ± 0.037 |
| Row-copying control | 0.291 ± 0.003 | 1.044 ± 0.138 | 0.494 ± 0.028 |
| Independent sampling | 0.141 ± 0.016 | 3.967 ± 0.351 | 0.676 ± 0.007 |
| Copulas + rank adapter | 0.150 ± 0.016 | 1.252 ± 0.258 | 0.523 ± 0.049 |
| DataSynthesizer BN | 0.230 ± 0.038 | 1.441 ± 0.211 | 0.559 ± 0.040 |
| arfpy | 0.286 ± 0.023 | 1.471 ± 0.118 | 0.528 ± 0.039 |

![Measured utility across three domains](benchmarks/results/utility_comparison.png)

## Predictive utility: linear model sensitivity check

| Method | Banking logistic AP ↑ | Student ridge MAE ↓ | Wine ridge MAE ↓ |
|---|---:|---:|---:|
| Real training reference | 0.283 ± 0.009 | 1.236 ± 0.162 | 0.491 ± 0.035 |
| Row-copying control | 0.269 ± 0.019 | 1.232 ± 0.189 | 0.499 ± 0.031 |
| Independent sampling | 0.153 ± 0.017 | 3.874 ± 0.659 | 0.679 ± 0.030 |
| Copulas + rank adapter | 0.164 ± 0.017 | 1.234 ± 0.178 | 0.507 ± 0.040 |
| DataSynthesizer BN | 0.237 ± 0.015 | 1.288 ± 0.207 | 0.551 ± 0.041 |
| arfpy | 0.287 ± 0.015 | 1.430 ± 0.043 | 0.510 ± 0.041 |


## Fidelity, runtime and copying diagnostics

Values are means across seeds. KS and TV compare individual synthetic columns with the held-out set; correlation error covers numeric Spearman correlations only. Categorical/continuous dependence and higher-order interactions are not fully measured here. N/A means no categorical columns, not a perfect score. Timing includes fitting, sampling and normalization, excludes installation/download and downstream predictor fitting. Real/copy timings are not model-training benchmarks.

| Dataset | Method | Numeric KS ↓ | Categorical TV ↓ | Numeric correlation MAE ↓ | Fit/sample seconds | Exact training-row match | Rows repaired |
|---|---|---:|---:|---:|---:|---:|---:|
| bank | Real training reference | 0.024 | 0.015 | 0.025 | 0.008 | 1.0000 | 0.000 |
| bank | Row-copying control | 0.031 | 0.017 | 0.031 | 0.008 | 1.0000 | 0.000 |
| bank | Independent sampling | 0.025 | 0.016 | 0.065 | 0.010 | 0.0002 | 0.000 |
| bank | Copulas + rank adapter | 0.048 | 0.017 | 0.033 | 0.064 | 0.0005 | 0.584 |
| bank | DataSynthesizer BN | 0.348 | 0.017 | 0.059 | 5.202 | 0.0000 | 0.000 |
| bank | arfpy | 0.078 | 0.019 | 0.031 | 20.696 | 0.0002 | 1.000 |
| student | Real training reference | 0.089 | 0.032 | 0.078 | 0.005 | 1.0000 | 0.000 |
| student | Row-copying control | 0.097 | 0.034 | 0.081 | 0.005 | 1.0000 | 0.000 |
| student | Independent sampling | 0.093 | 0.040 | 0.286 | 0.005 | 0.0000 | 0.000 |
| student | Copulas + rank adapter | 0.104 | 0.038 | 0.102 | 0.025 | 0.0045 | 0.254 |
| student | DataSynthesizer BN | 0.115 | 0.042 | 0.124 | 2.850 | 0.0023 | 0.000 |
| student | arfpy | 0.109 | 0.042 | 0.128 | 2.803 | 0.0034 | 1.000 |
| wine | Real training reference | 0.046 | N/A | 0.047 | 0.004 | 1.0000 | 0.000 |
| wine | Row-copying control | 0.054 | N/A | 0.051 | 0.004 | 1.0000 | 0.000 |
| wine | Independent sampling | 0.051 | N/A | 0.225 | 0.005 | 0.0000 | 0.000 |
| wine | Copulas + rank adapter | 0.052 | N/A | 0.057 | 0.030 | 0.0000 | 0.003 |
| wine | DataSynthesizer BN | 0.097 | N/A | 0.120 | 3.266 | 0.0000 | 0.000 |
| wine | arfpy | 0.079 | N/A | 0.087 | 5.535 | 0.0000 | 0.912 |


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

<!-- Source reference definitions generated from evidence/sources.json -->
[P01]: https://papers.neurips.cc/paper_files/paper/2019/hash/254ed7d2de3b23ab10936522dd547b78-Abstract.html
[P02]: https://faculty.washington.edu/billhowe/publications/pdfs/ping17datasynthesizer.pdf
[P03]: https://www.jstatsoft.org/article/view/v074i11
[P04]: https://proceedings.mlr.press/v206/watson23a.html
[P05]: https://arxiv.org/abs/2201.12677
[P06]: https://arxiv.org/abs/2108.04978
[P07]: https://www.usenix.org/conference/usenixsecurity22/presentation/stadler
[P08]: https://www.nature.com/articles/s41746-024-01359-3
[P09]: https://proceedings.mlr.press/v202/kotelnikov23a/kotelnikov23a.pdf
[P10]: https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9750610639c3e7a849cff746bf60dbd-Abstract-Conference.html
[P11]: https://arxiv.org/abs/2210.06280
[P12]: https://arxiv.org/abs/2302.02041
[P13]: https://proceedings.neurips.cc/paper/2019/hash/c9efe5f26cd17ba6216bbe2a7d26d490-Abstract.html
[P14]: https://arxiv.org/abs/1909.13403
[P15]: https://arxiv.org/abs/2301.07573
[P16]: https://arxiv.org/abs/2607.03926
[P17]: https://proceedings.mlr.press/v244/decruyenaere24a.html
[P18]: https://arxiv.org/abs/2406.14541
[T01]: https://github.com/sdv-dev/Copulas/tree/83a004b63323026e47c11d683695f23c5f804412
[T02]: https://github.com/DataResponsibly/DataSynthesizer/tree/b969f618015d6313d03e109ad58aae2f8b12124d
[T03]: https://github.com/vanderschaarlab/synthcity/tree/23f322fe381326ed01c41b13d469a06e38cce545
[T04]: https://github.com/opendp/smartnoise-sdk/tree/677d0bb13ed6f51941739693f3d528eefc6efacf
[T05]: https://github.com/sdv-dev/SDV/tree/cb6229d83921a1cf35e7cc5b4f947bc0e03699bd
[T06]: https://github.com/sdv-dev/CTGAN/tree/66e5686fbc55a55eb137253dce115946f5785ba2
[T07]: https://github.com/sdv-dev/SDMetrics/tree/d35c170f1570387cf42085fc6c9316dad5c23a7a
[T08]: https://github.com/synthetichealth/synthea/tree/d9d07a6eef91ee5144293b42ab64224d84d124f8
[T09]: https://github.com/alan-turing-institute/tapas/tree/a7069d7e040828db0da174d1b003fa03a98e5453
[T10]: https://github.com/joke2k/faker/tree/975dd2a11d7f083cb028e2f07478ab401b5fde17
[T11]: https://github.com/worldbank/REaLTabFormer/tree/73f239643f9ea5abc877f685ce927e986302ac2d
[T12]: https://github.com/yandex-research/tab-ddpm/tree/b476257dd460b778ba09eb97f7a51d6490fa17f8
[T13]: https://github.com/tabularis-ai/be_great/tree/616b2e74b396fa1f9c7ab4412b9928eec849159a
[T14]: https://github.com/bips-hb/arfpy/tree/8b63c1b3999981125b4af2828ff52cba8e29169d
[T15]: https://github.com/DLR-RM/BlenderProc
[T16]: https://github.com/argilla-io/distilabel
[T17]: https://simpy.readthedocs.io/en/latest/
[T18]: https://www.synthpop.org.uk/about-synthpop.html
[N01]: https://csrc.nist.gov/pubs/sp/800/226/final
[N02]: https://www.nist.gov/services-resources/software/sdnist-synthetic-data-report-tool
[D01]: https://archive.ics.uci.edu/dataset/222/bank+marketing
[D02]: https://archive.ics.uci.edu/dataset/320/student+performance
[D03]: https://archive.ics.uci.edu/dataset/186/wine+quality
[D04]: https://docs.smartnoise.org/synth/index.html
