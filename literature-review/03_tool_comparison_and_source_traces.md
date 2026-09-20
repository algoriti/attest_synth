# Tool comparison and implementation findings

This matrix separates documented scope, inspected implementation, and local execution. A “not run” entry is not an installation failure. The exact upstream licenses and commits are archived in [the evidence manifest](evidence/repository_manifest.json); installed-package licenses are in [installed evidence](evidence/installed/manifest.json).

## Capability and reuse matrix

| Tool | Inputs / principal role | Modality and limitations | License inspected | Local status | Recommended role |
|---|---|---|---|---|---|
| Faker [T10] | Providers, locale and rules; no source records needed | Fake field values; dependencies need our rules | MIT | Executed in retail example | Initial schema-only field providers |
| arfpy [T14] | Fit mixed table; density estimation; sample | Single-table; explicit type/constraint wrapper needed | MIT | 9 generation runs | First learned adapter, subject to task report |
| DataSynthesizer [T02] | Describe → Bayesian/independent generation → inspect | Single-table CSV; discretization choices matter | MIT | 9 correlated-mode runs | Transparent baseline and teaching/reference engine |
| Copulas [T01] | Numerical dependence model | Mixed fields require transformations; not a relational platform | BSL 1.1 | 9 runs through custom rank adapter | Technical comparator; not default permissive foundation |
| Synthcity [T03] | Plugin framework and evaluation | Several tabular/sequence/survival families; missing data require preprocessing | Apache-2.0 | Source inspected; not run | Optional isolated worker for later model families |
| SmartNoise Synth [T04] | DP mechanisms and transformations | Model-specific discrete domains/bins and accounting | MIT | Source inspected; not run | First DP adapter candidate; activation requires dedicated validation |
| SDV [T05] | Integrated metadata, transformations and synthesis | Community/commercial capabilities must be checked per feature/version | BSL 1.1 | Documentation/license | Architectural reference; deployment-specific licensing decision |
| Standalone CTGAN [T06] | CTGAN and TVAE implementation | Learned tables; no default formal privacy | BSL 1.1 | Paper/repository/license | Neural comparison option after license decision |
| synthpop [T18] | Sequential conditional synthesis in R | R integration and customized modeling | Not independently pinned in this review | Paper/official overview | Important later statistical comparator |
| REaLTabFormer [T11] | Transformer tabular/parent-child models | Verify exact relational topology; do not assume arbitrary database support | MIT | Paper/README; attempted source path failed | Relational extension candidate |
| TabDDPM [T12] | Mixed-type diffusion | Research training/evaluation workflow; no DP by default | MIT | Paper/README/license | Later neural comparator |
| GReaT / be_great [T13] | Fine-tune language model on rows | Model weights and training data have additional requirements | MIT code | Paper/README/license | Research alternative, not initial copilot implementation |
| Synthea [T08] | Domain rules and population simulation | Healthcare-specific assumptions and formats | Apache-2.0 | README/license | Optional domain pack, not the general core |
| SDMetrics [T07] | Quality/evaluation measures | Metrics require appropriate metadata and interpretation | MIT | README/license | Candidate reporting dependency; not run locally |
| TAPAS [T09] | Adversarial privacy audit | Attack setup, shadow training and threat model required | MIT | README/license | Audit harness candidate; not a release certificate |

Additional modality references: SimPy for discrete-event processes [T17], Distilabel for text/data-generation pipelines [T16], BlenderProc for rendered labeled images [T15], TimeGAN and DoppelGANger for sequences [P13], [P14], and TabSyn as a diffusion comparator [P10]. These were screened, not dependency-qualified or executed.

## A consequential license correction

The current captured SDV, CTGAN and Copulas license files use BSL 1.1 with an additional grant that excludes specified commercial synthetic-data services. Copulas 0.14.1's installed distribution also contains BSL. These files state a four-year change mechanism to MIT; dates apply per release. This review does not determine that a particular old version has changed license or that every government deployment is restricted.

SDMetrics is MIT in its own captured file. Synthcity, DataSynthesizer and arfpy must also be judged on their own files and dependencies. Never infer the entire ecosystem's license from one package. Code licenses do not settle rights in model weights, source datasets, third-party assets or generated outputs. [Captured license evidence](evidence/repository_manifest.json)

## Source trace A: DataSynthesizer 0.1.13 (executed)

Sources: [DataDescriber](evidence/installed/DataSynthesizer.DataDescriber.py), [PrivBayes helpers](evidence/installed/DataSynthesizer.lib.PrivBayes.py), [DataGenerator](evidence/installed/DataSynthesizer.DataGenerator.py).

1. `describe_dataset_in_correlated_attribute_mode()` first invokes independent description, processing supplied categorical/type/key information.
2. `encode_dataset_into_binning_indices()` constructs discrete representations.
3. `greedy_bayes()` chooses a network with the requested parent bound.
4. `construct_noisy_conditional_distributions()` builds distributions stored in the description.
5. The generator reads the saved description, draws root and conditional values, and converts them to output values.

The API documents `epsilon=0` as disabling privacy. That is the setting used here. The parameter's name must not trick the platform into labeling it “perfect privacy.” This interpretation comes from the inspected implementation, not an assumption about the mathematical definition.

**Integration consequence:** persist description/version/transform settings; expose bins and categorical semantics; never release a learned description merely because it is metadata. The benchmark's poor banking numerical fidelity warrants investigating binning before promoting this configuration.

## Source trace B: Synthcity plugin flow (inspected, not executed)

Source: [captured plugin.py](evidence/vanderschaarlab__synthcity/src/synthcity/plugins/core/plugin.py), upstream commit in the manifest. `fit()` begins around line 172; `generate()` around 274; `_safe_generate()` around 395.

`fit()` wraps a dataframe in `GenericDataLoader`, captures data information and schemas, encodes tabular columns, optionally compresses/caches data, and delegates to `_fit()`. `generate()` builds schema constraints, calls `_generate()`, reverses transforms and checks constraints. `_safe_generate()` repeatedly samples and filters for a bounded number of attempts. Its final `.head(count)` does not itself guarantee that enough valid rows were obtained.

**Integration consequence:** check returned row counts as well as validity; expose rejection/exhaustion; isolate workspace/cache files within the data boundary; test each plugin's actual capabilities. A condition used for neural training is not automatically a hard constraint.

The [CTGAN plugin](evidence/vanderschaarlab__synthcity/src/synthcity/plugins/generic/plugin_ctgan.py) constructs Synthcity's `TabularGAN`, calls its `fit()`, and wraps model generation in `_safe_generate()`. It is not simply an import of the standalone `ctgan` package. Licensing and results cannot be transferred between implementations solely because their algorithm name matches.

## Source trace C: SmartNoise preprocessing and MST (inspected, not executed)

Sources: [base.py](evidence/opendp__smartnoise-sdk/synth/snsynth/base.py), [table transformer](evidence/opendp__smartnoise-sdk/synth/snsynth/transform/table.py), [mst.py](evidence/opendp__smartnoise-sdk/synth/snsynth/mst/mst.py).

`_get_train_data()` creates or accepts a transformer. When fitting needs private bounds, it checks preprocessing budget, fits the transformer, reads its odometer and reduces the remaining training epsilon. MST then needs finite categorical cardinalities, constructs an `mbi` domain and dataset, fits its mechanism and inverse-transforms generated values.

**Integration consequence:** the DP contract must cover transforms and model, not just expose an epsilon textbox. Use fixed approved domains where appropriate; account for private estimates otherwise. Source inspection is not an audit proving end-to-end DP or successful execution.

## Source trace D: arfpy 0.1.1 (executed)

Source: [installed arf.py](evidence/installed/arfpy.arf.py).

The constructor encodes object/category columns, initializes synthetic rows by marginal resampling, and fits a real-versus-synthetic random forest. Iterative generation/discrimination produces partitions; `forde()` estimates leaf distributions and `forge(n)` samples output. We passed categorical metadata explicitly, including the binary target.

Generated numeric columns can require integer restoration and bounds enforcement. The benchmark records this repair rate. The implementation emitted pandas future warnings under the captured environment; warnings are retained in [run_details.json](benchmarks/results/run_details.json). Successful runs are not evidence of compatibility with arbitrary future pandas/NumPy releases.

**Integration consequence:** pin the runtime, add contract tests around types/row count/serialization and support a separate worker. ARF has no DP guarantee in this configuration.

## Source trace E: Copulas adapter (executed)

Sources: [installed Gaussian implementation](evidence/installed/copulas.multivariate.gaussian.py), [our adapter](benchmarks/run_benchmark.py).

The library fits marginal models and a dependence matrix, then samples and inverse-transforms. Our adapter first maps continuous ranks and category frequency intervals into normal scores and later reverses those mappings. This is an explicitly authored mixed-type adapter; it must not be attributed to stock SDV. Category order sensitivity is an unresolved limitation and should be tested before adopting such an adapter.

## Dependencies and maintenance evidence

The captured [PyPI metadata](evidence/pypi_metadata.json) lists Synthcity 0.2.12 with `numpy<2` and `torch>=2.1,<2.3`, among many dependencies. Our benchmark uses NumPy 2.3.5 and no PyTorch. Therefore integrating Synthcity into the same environment would require a deliberate separate dependency solution. We did **not** attempt installation or claim failure.

SmartNoise Synth 1.0.8's metadata includes `mbi`, `opacus`, `pac-synth` and `smartnoise-sql`. The inspected repository MST source uses `mbi` interfaces; older website examples and current repository code should not be assumed to match a pinned wheel. This is a concrete version-compatibility check for the next DP experiment.

The [generated inventory](evidence/software_inventory.md) records default-branch dates and selected release versions. TAPAS's captured default-branch commit is from 2023; that is a maintenance signal requiring testing, not proof it is unusable. Small packages can be easier to integrate but can also have fewer maintainers and less compatibility coverage.

## Selection criteria

Use hard gates before ranking: license fit, supported modality, supported source-data access mode, ability to enforce required constraints, compatible runtime, and required privacy mechanism. For eligible tools compare reproducible task utility, failure rates, repair cost, resource usage and maintainability. No invented weighted “best tool” score is used here.

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
