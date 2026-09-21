# Platform benchmark after the review fixes

27 trials: three public datasets × three seeds (11, 29, 47) × ARF, independent columns and a copying control. All trials completed and all structural checks passed. The control is registered only in the benchmark process, not in the application.

This is a new platform benchmark, separate from the earlier literature-review experiment. Each dataset uses at most 1,200 deduplicated records and a fixed declared schema; it does not discover policies from the full dataset. The platform splits real rows before fitting the generator. A random forest trained on synthetic data, real training data, and independently sampled data is tested on the same real holdout. These are small exploratory comparisons, not a universal engine ranking or privacy assessment.

| Dataset / metric | Real training | Independent | ARF | Copy control |
|---|---:|---:|---:|---:|
| bank / average_precision | 0.378 | 0.143 ± 0.023 | 0.304 ± 0.042 | 0.322 ± 0.030 |
| student / mae | 0.994 | 3.967 ± 0.351 | 1.550 ± 0.258 | 1.044 ± 0.138 |
| wine / mae | 0.497 | 0.684 ± 0.021 | 0.527 ± 0.040 | 0.513 ± 0.028 |

Values are means over three seeds; ± is the sample standard deviation. Higher average precision is better; lower MAE is better. ARF beat independent sampling on these tasks. Copying whole training rows also preserved predictive signal, illustrating why these utility measurements cannot establish privacy.

Full per-run evidence includes train/test hashes, marginal and numerical correlation metrics, exact-match diagnostics, repairs, elapsed time and peak process RSS. Each trial runs in a fresh process; peak RSS includes the interpreter and imported libraries. No membership-inference or entity-level privacy attack was run. These flat datasets do not establish longitudinal or relational learned fidelity.

Reproduce from the repository root:

```bash
.venv/bin/python platform/backend/benchmarks/run_platform_benchmark.py
```

[Machine-readable results](results/summary.json). The bank, student and wine public-data sources and acquisition details remain documented in `literature-review/benchmarks/data/README.md`.

## Hosted assistant requirement check

`check_employee_assistant.py` sends the saved public scenario in `prompts/employee_behavioral_500_12_months.txt` to the configured Groq endpoint, validates the proposal, generates it, and records requirement-level evidence. The 21 September 2026 run completed in 25.747 seconds: 500 employees; all six supported requested entities; no missing requested fields or extra entities; five relationship-owned foreign keys; 130,795 generated rows; and all final constraints passing. Monthly employee-period summaries were disclosed and omitted because the current engine cannot calculate them across several activity tables. They were not replaced with random indicators.

The credential-free machine result is [assistant_employee_behavioral_check.json](results/assistant_employee_behavioral_check.json). Model output remains stochastic, so this is a regression case and observed result rather than a guarantee that every prompt will have the same coverage.
