# Remaining experiments and work performed

## What was completed in this review

1. Read both supplied GPT discussions, preserved the general-purpose objective, and converted claims into questions about inputs, capabilities, privacy and reuse.
2. Searched original publications, official project documentation and current software evidence. Created a 42-entry annotated source register, with read depth and limitations.
3. Captured 14 repositories' README/license evidence at exact commits, package release/dependency metadata, eight upstream source files and five executed-library source modules.
4. Checked the licenses of the actual installed benchmark packages. Discovered that Copulas and standalone CTGAN, as well as SDV, use BSL in the captured current versions.
5. Created an isolated temporary Python environment. Installed Copulas, DataSynthesizer, arfpy, Faker and plotting dependencies. The environment inherited available numerical packages; exact versions are recorded.
6. Downloaded three UCI datasets. Investigated mirrors during a slow response, rejected an altered banking dataset, then restored/verified primary UCI inputs before any final benchmark run.
7. Wrote and executed 54 comparative runs with 108 downstream predictor fits, plus three schema-only scenarios producing 3,000 rows. Recorded per-run data, settings, warnings, split indices and timings.
8. Produced tables and PNG/SVG charts from recorded measurements. Separated copying diagnostics from privacy claims and documented normalization.
9. Drafted a platform recommendation, engine contract, specification schema, examples and validation roadmap. These drafts do not mean the platform or LLM integration has been implemented.
10. Verified artifact integrity, benchmark splits/results, JSON examples and local document links. The machine-readable verification result is in `benchmarks/results/verification.json`.

## Next experiments, in decision order

| Question | Experiment | Decision supported |
|---|---|---|
| Does the first adapter remain useful on untuned data? | Lock current settings; add at least three new domain/task datasets, multiple sample sizes and a new held-out evaluation | Keep, replace or supplement ARF |
| Does preprocessing destroy meaningful missingness? | Public data with real missingness plus controlled missingness scenarios; compare masks, associations and task utility | Imputation/mask strategy and supported inputs |
| Are rare groups retained? | Prespecified category frequencies and subgroup tasks; report coverage and uncertainty, including unseen categories | Capability limits and warnings |
| Can the engine enforce user rules efficiently? | Cross-column constraints, impossible constraints and low-acceptance conditions; measure rejection/repair bias and count shortfalls | Constraint engine and failure behavior |
| Is a copula adapter robust to representation choices? | Permute nominal-category ordering and vary tied-rank transforms under fixed data splits | Whether observed utility is encoding-dependent |
| Would neural synthesis improve utility enough to justify cost? | Reproduce one CTGAN/TVAE plugin and one diffusion candidate in isolated environments; fixed compute budgets and equal data access | Optional neural adapter selection |
| Can we demonstrate correctly configured DP? | Pinned SmartNoise mechanism; public fixed domains; separate epsilon settings, protected unit and accounting; utility and audit reports | Whether to expose a DP workflow |
| Can attackers learn individual information? | Stated membership and attribute inference threats, suitable attack baselines and multiple targets; preserve audit datasets | Bounds of empirical privacy evidence |
| Is synthetic augmentation useful? | Small real training subsets versus the same subsets plus generated records; identical held-out data; compare to ordinary resampling | Whether to advertise scarcity/augmentation benefit |
| Can analytical questions be answered? | Prespecified grouped counts, conditional means, joins where supported and tail queries | Analytics-use qualification |
| Does the LLM reduce user effort? | Cross-domain requests with expected specifications; form versus copilot comparison; errors, corrections and time | LLM interface value and release readiness |
| Do nontechnical users understand limitations? | Small representative user study with report-comprehension tasks | Report design and usability |

The tests above are a proposal, not work silently counted as completed. Privacy attacks and DP accounting are necessary before sensitive-data release claims, but public-data prototyping can proceed now with explicit labeling.

## What must be fixed before private institutional deployment

Define the protected entity and access/release policy with the institution. Inventory raw records, profiles, schemas, model artifacts, caches, prompts, logs and released metrics. Bind every worker to the approved boundary. Check all data-dependent transformations and composition across retraining. Test the actual installed mechanism and selected threat model. Document authorized downstream uses and utility limits.

This is a future deployment requirement, not a request for approval to finish the current review. No private institutional data was used here.

## Known gaps in the deliverable

- Structured-data literature and source inspection are much deeper than text/image/audio/graph coverage.
- Several papers were screened through abstracts or selected sections, rather than read and reproduced in full; the source register identifies these.
- No systematic-review completeness claim or meta-analysis was performed.
- The benchmark is narrow in size, features, tasks, hyperparameters and geography; three different domains are not all possible use cases.
- Recommendations prioritize a viable permissive first integration, not the highest possible score on every task.
- Source code was inspected at repository HEAD where recorded, while local experiments used released packages; neither silently substitutes for the other.
- Private deployment, formal DP, adversarial audits, human usability and LLM behavior remain unevaluated.

## Proposed first implementation ticket

**Implement the specification validator and engine adapter contract with rule and ARF adapters.**

Inputs: the draft schema/examples, benchmark preprocessing decisions and captured versions. Output: a local API/CLI accepting a reviewed specification and approved CSV where required, returning a dataset plus a machine-readable evidence report. Acceptance: three contrasting domain examples, explicit unsupported-request handling, no unreported invalid rows, correct row counts, saved provenance, and no unsupported privacy claim. Add the conversational UI once this path is inspectable and reliable.

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
