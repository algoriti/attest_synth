# Literature synthesis: what the platform must understand

## 1. “Useful synthetic data” is a purpose-dependent claim

A software tester needs valid structure and deliberate edge cases. An analyst needs accurate answers to selected queries. An ML practitioner needs retained predictive relationships. A statistician may need valid estimates and uncertainty. A data custodian needs an explicit disclosure model. These objectives must appear in the request specification and report.

The CTGAN paper evaluates both distribution modeling and prediction on real test data, giving a precedent for task-based assessment [P01]. Research on inferential utility separately examines statistical estimation [P17]. TabQueryBench, a July 2026 preprint, evaluates SQL-shaped query behavior and reports deficiencies that general similarity metrics can miss [P16]. These sources support multiple evaluations, not a universal “quality percentage.”

**Design implication (proposed):** users select a purpose—testing, analytics, ML development, teaching, or a specified simulation. Results state which purposes were actually evaluated. Preserving association does not establish a causal effect or treatment-response simulator.

## 2. Information source determines what generation can establish

| Input | Suitable family | Claim that can be investigated |
|---|---|---|
| Only types, fields and rules | Faker and rule-based sampling | Structural validity and scenario coverage |
| Public or approved aggregates | Distribution fitting/calibration or domain simulation | Agreement with supplied summaries |
| Individual records | Statistical, tree, neural or DP synthesis | Fidelity and task utility relative to that source |
| Process knowledge | Simulation | Behavior under explicit process assumptions |

A schema does not identify a joint distribution. Aggregate marginals also leave many possible relationships undetermined. An LLM proposing one possible relationship has not discovered population evidence. The specification must distinguish assumptions from measured estimates.

DataSynthesizer's original architecture separates describing a dataset, sampling from its description, and inspecting results [P02]. Faker provides locale-aware fake values without fitting the user's population [T10]. Synthea supplies patient simulation through modular rules; SimPy provides general discrete-event simulation machinery [T08], [T17]. Neither domain realism nor a general simulation model arrives automatically from a schema.

**Reuse decision:** preserve separate schema/rule and learned workflows. Do not implement a fake `fit()` requirement for a generator that needs no records.

## 3. Statistical and tree methods deserve first-class evaluation

Independent marginal sampling is inexpensive and transparent, but discards dependence. It is an essential lower baseline, not a realistic general solution.

A Gaussian copula models marginal distributions separately from dependence in transformed space. The numerical Copulas library exposes fitting and sampling; mixed-type handling still needs an adapter [T01]. Nominal category encoding can introduce artificial order. Rounding, inverse transforms and constraints change the output distribution; their effects belong in the evaluation.

Bayesian networks factor a joint distribution into conditional distributions. DataSynthesizer exposes this structure, making it educational and relatively inspectable [P02]. Sparse combinations and discretization are practical limitations. Increasing parent count can increase both expressiveness and computational cost.

synthpop uses sequential conditional synthesis and allows the user to customize the synthesis process [P03]. It remains an important R-based comparator even though this experiment uses Python. Its existence is evidence against treating neural generators as the default starting point.

Adversarial random forests alternate generation and discrimination and estimate densities within learned partitions. The original ARF paper reports favorable speed/quality results on its benchmarks; those are authors' results, not reproduced speedup claims here [P04]. The Python implementation `arfpy` is a small, MIT-licensed integration candidate [T14].

**Hypothesis tested locally:** can affordable dependency-aware methods outperform independent sampling across distinct domains? See the benchmark report for actual results and limitations.

## 4. Neural generators expand the search space, not the guarantees

CTGAN addresses multimodal continuous features and imbalanced categorical data using specialized transformation and conditional sampling/training. The same paper introduces TVAE as a comparison [P01]. An algorithm name does not establish the behavior, license or performance of every implementation bearing that name.

TabDDPM combines diffusion mechanisms suitable for mixed tabular features [P09]. TabSyn uses a learned latent representation followed by diffusion [P10]. Both deserve inclusion in a later model comparison; omitting them while claiming an exhaustive contemporary review would be misleading. They were literature-screened, not trained in this work.

Neural fitting introduces model selection, training cost and reproducibility questions. A schema-valid sample is not evidence that rare groups, higher-order dependencies or downstream decisions have been preserved.

**PoC decision:** begin with measured CPU-capable approaches. Add one neural comparator in a separate worker after reproducing its environment and matching evaluation budgets. Do not compare one undertrained neural run to extensively tuned classical models and call that a fair benchmark.

## 5. LLMs can be an interface or a generator—different roles

GReaT fine-tunes an autoregressive language model on representations of rows and supports conditional generation [P11]. This is materially different from asking an untrained assistant to invent a CSV. Separate original research reports limitations of off-the-shelf and conventionally fine-tuned LLMs for tabular dependencies [P18]. These results concern particular settings; neither proves that LLMs always succeed or always fail.

For this platform, the immediate LLM role is proposed as requirement translation, ambiguity detection and explanation. This is an engineering decision, not a performance finding reproduced in this review.

**Requirements:** typed structured output; bounded constraint operators; explicit provenance; reviewable specification changes; no arbitrary generated code execution; no authority to invent privacy settings. Report extraction accuracy and user corrections in a future evaluation. A well-formed JSON document can still encode an incorrect interpretation.

A local or approved remote LLM can be swapped behind the same interface. Raw records are not necessary for the initial copilot workflow. Data-derived metadata still requires appropriate handling.

## 6. Relationships and time cannot be reduced to arbitrary CSVs

REaLTabFormer introduces tabular and relational transformer models [P12]. Its relational scope must be checked for the exact parent-child structure; this review does not infer arbitrary cyclic database support. Generating two valid tables independently does not preserve their joins or parent-child cardinality distribution.

TimeGAN learns temporal structure through an embedding and supervised/adversarial objectives [P13]. DoppelGANger targets networked time-series challenges such as longer dependencies and relationships between attributes and sequences [P14]. Static table scores are insufficient to validate either.

**Extension gates:** relational output needs primary/foreign keys, orphan counts, join-query fidelity and cardinality distributions. Time-series output needs time ordering, sampling intervals, autocorrelation, seasonality, cross-series relationships and forecasting evaluation using time-respecting splits. These are proposed requirements, not completed benchmarks.

## 7. Differential privacy is a pipeline property

AIM selects and privately measures useful queries, then synthesizes data to approximate those measurements [P05]. MST belongs to the marginal-measurement/probabilistic-model family and has evidence from the NIST challenge [P06]. These methods are important alternatives to private neural training.

SmartNoise documents both synthesis and transformation controls [T04]. Our captured source shows preprocessing spend being subtracted before training. Bounds, domains, imputation, model selection, repeated fits and released metrics must be considered when making an end-to-end claim.

NIST SP 800-226 discusses how mathematical guarantees translate into deployed systems [N01]. For the platform this means specifying the protected entity, adjacency, contribution limits, epsilon/delta where applicable, accountant, data-dependent steps and all released artifacts. Repeated sampling from an already DP model differs from retraining on private data; the latter can spend additional budget. Reproducible public benchmark seeds must not become publicly fixed randomness for a private DP release.

**PoC decision:** a documented DP adapter is a planned extension, not an enabled “private mode” backed by this benchmark. Our DataSynthesizer experiment explicitly disables its noise mechanism and supports no privacy guarantee.

## 8. Privacy auditing and utility evaluation are separate

Stadler et al. empirically demonstrate inference risks and unpredictable privacy–utility outcomes for evaluated synthesizers [P07]. The medical scoping review reports inadequate residual-risk assessment and warns about relying on similarity metrics [P08]. Healthcare motivates that review, but the distinction between similarity and disclosure risk applies to our platform design across domains.

TAPAS provides an adversarial audit framework [T09]. Attacks need stated adversary knowledge, access to model or data, target selection and appropriate controls. A failed attack establishes a limit of that test, not proof of safety. Exact duplicate checks are useful diagnostics but cannot detect all inference leakage.

SDMetrics supplies evaluation primitives [T07]; SDNist supplies a report-oriented evaluation reference [N02]. Both inform our report design. No single averaged score should hide a rare-category failure, excessive copying or an unusable downstream model.

## 9. General purpose requires modality-specific engines and evidence

| Capability | Candidate/reference | Additional validation before support |
|---|---|---|
| Structured scenarios | Faker + explicit rules | Structural and semantic constraints |
| Learned tables | ARF, Bayesian, copula, neural and DP methods | Fidelity, utility, disclosure tests |
| Relational data | REaLTabFormer, SDV concepts | Keys, joins and conditional cardinality |
| Time series | TimeGAN, DoppelGANger | Temporal structure and forecast usefulness |
| Process simulation | SimPy; Synthea as a domain example | Process calibration and domain review |
| Text/instruction datasets | Distilabel | Factuality, diversity, contamination and task evaluation |
| Images with labels | BlenderProc | Rendered labels, domain gap and target vision task |
| Audio, graphs, geospatial data | Separate specialist review required | Modality-specific criteria, not inferred tabular support |

Distilabel and BlenderProc were screened through their official projects [T16], [T15]. These are extension references, not selected dependencies. Model weights, assets and generated-data rights must be checked separately from code licenses.

## 10. Findings that change our design

1. Keep generation purpose, data modality, available evidence, privacy requirement and execution location as separate dimensions.
2. Build a common specification and explicit engine capability contract; refuse unsupported requests.
3. Prefer measured small integrations over assuming the largest framework is the best core.
4. Evaluate repaired output but disclose raw violations and repair rates.
5. Keep source provenance and version information beside every result.
6. Treat statistical utility, predictive utility, inferential utility and privacy as distinct claims.
7. Develop across domains while expanding technical capabilities in stages.

All paper and tool identifiers link through the [source register](07_sources.md). Empirical conclusions are in [the local benchmark report](04_benchmark_report.md), not in the published-findings discussion above.

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
