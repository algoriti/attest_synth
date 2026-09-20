# Source register and annotated bibliography

Accessed 20 September 2026. This register distinguishes original research, implementation evidence and limited screening. It contains 42 entries: 18 research publications/preprints and 24 software, guidance or data references. The engineering review is not an exhaustive systematic review.

| ID | Source / year | Read depth | What it supports and does not establish |
|---|---|---|---|
| P01 | [Xu et al. — Modeling Tabular Data using Conditional GAN](https://papers.neurips.cc/paper_files/paper/2019/hash/254ed7d2de3b23ab10936522dd547b78-Abstract.html) (2019) | Publisher abstract and paper introduction/method excerpt | Mixed feature types, conditional GAN approach, TVAE comparison and task-based evaluation; published benchmark not reproduced. |
| P02 | [Ping, Stoyanovich and Howe — DataSynthesizer: Privacy-Preserving Synthetic Datasets](https://faculty.washington.edu/billhowe/publications/pdfs/ping17datasynthesizer.pdf) (2017) | Paper architecture/method sections plus installed source | Description/generation/inspection separation and independent/Bayesian modes; local execution is separately documented. |
| P03 | [Nowok, Raab and Dibben — synthpop: Bespoke Creation of Synthetic Data in R](https://www.jstatsoft.org/article/view/v074i11) (2016) | Publisher page and author project methodology | Sequential conditional synthesis is an established alternative; no local R experiment. |
| P04 | [Watson et al. — Adversarial Random Forests for Density Estimation and Generative Modeling](https://proceedings.mlr.press/v206/watson23a.html) (2023) | Publisher abstract; Python implementation inspected and run | Tree-based iterative generation/discrimination and reported authors’ benchmark results; no reproduced two-orders-of-magnitude claim. |
| P05 | [McKenna et al. — AIM: An Adaptive and Iterative Mechanism for Differentially Private Synthetic Data](https://arxiv.org/abs/2201.12677) (2022) | Original author abstract screened | Adaptive private query measurement and generation; no local AIM utility or privacy result. |
| P06 | [McKenna et al. — Winning the NIST Contest: A Scalable and General Approach to Differentially Private Synthetic Data](https://arxiv.org/abs/2108.04978) (2021) | Original author abstract screened | MST/NIST-MST context; no assertion of universal superiority. |
| P07 | [Stadler, Oprisanu and Troncoso — Synthetic Data: Anonymisation Groundhog Day](https://www.usenix.org/conference/usenixsecurity22/presentation/stadler) (2022) | Publisher abstract and original paper discovery | Empirical privacy/utility failure modes for evaluated models; not a theorem against all synthesis. |
| P08 | [A Scoping Review of Privacy and Utility Metrics in Medical Synthetic Data](https://www.nature.com/articles/s41746-024-01359-3) (2025) | Results/discussion retrieved earlier in this session; later fetch redirected | Evidence of evaluation gaps and limitations of similarity-based privacy measures. Healthcare scope is not the platform scope. |
| P09 | [Kotelnikov et al. — TabDDPM: Modelling Tabular Data with Diffusion Models](https://proceedings.mlr.press/v202/kotelnikov23a/kotelnikov23a.pdf) (2023) | Original abstract/method overview and repository | Mixed-feature diffusion family; not locally trained. |
| P10 | [Mixed-Type Tabular Data Synthesis with Score-based Diffusion in Latent Space (TabSyn)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9750610639c3e7a849cff746bf60dbd-Abstract-Conference.html) (2024) | Publisher abstract and official repository screened | Latent VAE plus diffusion approach; reported quality/speed not replicated. |
| P11 | [Borisov et al. — Language Models are Realistic Tabular Data Generators (GReaT)](https://arxiv.org/abs/2210.06280) (2023) | Original abstract and published ICLR paper excerpt | Fine-tuning for tabular synthesis and conditioning; distinct from a general chat assistant. |
| P12 | [Solatorio and Dupriez — REaLTabFormer: Generating Realistic Relational and Tabular Data using Transformers](https://arxiv.org/abs/2302.02041) (2023) | Original abstract and official repository/docs | Tabular and relational transformer approach; topology-specific validation still needed. |
| P13 | [Yoon, Jarrett and van der Schaar — Time-series Generative Adversarial Networks](https://proceedings.neurips.cc/paper/2019/hash/c9efe5f26cd17ba6216bbe2a7d26d490-Abstract.html) (2019) | Publisher abstract and method excerpt | Temporal embedding with supervised/adversarial objectives; not locally trained. |
| P14 | [Using GANs for Sharing Networked Time Series Data: Challenges, Initial Promise, and Open Questions (DoppelGANger)](https://arxiv.org/abs/1909.13403) (2019 preprint) | Original author abstract screened | Networked sequence fidelity and privacy challenges; local sensor scenario is not a replication. |
| P15 | [Qian et al. — Synthcity: Facilitating Innovative Use Cases of Synthetic Data in Different Data Modalities](https://arxiv.org/abs/2301.07573) (2023) | Original abstract plus current repository and plugin source | Common plugin access across model families; broad scope alone does not determine integration fit. |
| P16 | [Zhang et al. — TabQueryBench: A Query-Centric Benchmark for Synthetic Tabular Data](https://arxiv.org/abs/2607.03926) (2026 preprint) | Original abstract screened | Recent query-workload evaluation gap; no local reproduction or assumed peer review. |
| P17 | [Decruyenaere et al. — The Real Deal Behind the Artificial Appeal: Inferential Utility of Tabular Synthetic Data](https://proceedings.mlr.press/v244/decruyenaere24a.html) (2024) | Publisher abstract screened | Statistical inference deserves separate evaluation from prediction. |
| P18 | [Are LLMs Naturally Good at Synthetic Tabular Data Generation?](https://arxiv.org/abs/2406.14541) (2024 preprint) | Original abstract screened | Evidence of tabular-dependency limitations under the authors’ tested LLM setups; not a universal result. |
| T01 | [Copulas](https://github.com/sdv-dev/Copulas/tree/83a004b63323026e47c11d683695f23c5f804412) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T02 | [DataSynthesizer](https://github.com/DataResponsibly/DataSynthesizer/tree/b969f618015d6313d03e109ad58aae2f8b12124d) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T03 | [Synthcity](https://github.com/vanderschaarlab/synthcity/tree/23f322fe381326ed01c41b13d469a06e38cce545) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T04 | [SmartNoise SDK](https://github.com/opendp/smartnoise-sdk/tree/677d0bb13ed6f51941739693f3d528eefc6efacf) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T05 | [SDV](https://github.com/sdv-dev/SDV/tree/cb6229d83921a1cf35e7cc5b4f947bc0e03699bd) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T06 | [CTGAN](https://github.com/sdv-dev/CTGAN/tree/66e5686fbc55a55eb137253dce115946f5785ba2) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T07 | [SDMetrics](https://github.com/sdv-dev/SDMetrics/tree/d35c170f1570387cf42085fc6c9316dad5c23a7a) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T08 | [Synthea](https://github.com/synthetichealth/synthea/tree/d9d07a6eef91ee5144293b42ab64224d84d124f8) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T09 | [TAPAS](https://github.com/alan-turing-institute/tapas/tree/a7069d7e040828db0da174d1b003fa03a98e5453) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T10 | [Faker](https://github.com/joke2k/faker/tree/975dd2a11d7f083cb028e2f07478ab401b5fde17) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T11 | [REaLTabFormer](https://github.com/worldbank/REaLTabFormer/tree/73f239643f9ea5abc877f685ce927e986302ac2d) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T12 | [TabDDPM implementation](https://github.com/yandex-research/tab-ddpm/tree/b476257dd460b778ba09eb97f7a51d6490fa17f8) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T13 | [GReaT implementation](https://github.com/tabularis-ai/be_great/tree/616b2e74b396fa1f9c7ab4412b9928eec849159a) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T14 | [arfpy](https://github.com/bips-hb/arfpy/tree/8b63c1b3999981125b4af2828ff52cba8e29169d) (snapshot 2026-09-20) | README and license captured; source/execution where specified in tool report | Version-specific documented scope and license; see tool matrix and source traces. |
| T15 | [BlenderProc](https://github.com/DLR-RM/BlenderProc) (accessed 2026-09-20) | Official README screened; not pinned/run | Rendered labeled-image extension reference; assets and full dependency licensing not assessed. |
| T16 | [Distilabel](https://github.com/argilla-io/distilabel) (accessed 2026-09-20) | Official README screened; not pinned/run | Text-generation and feedback pipeline extension reference; model-specific rights still required. |
| T17 | [SimPy](https://simpy.readthedocs.io/en/latest/) (accessed 2026-09-20) | Official overview screened; not run | Discrete-event simulation capability, not a calibrated general domain model. |
| T18 | [synthpop project](https://www.synthpop.org.uk/about-synthpop.html) (accessed 2026-09-20) | Official author methodology overview | Sequential synthesis, customization and confirmation against original data. |
| N01 | [NIST SP 800-226 (March 2025 final)](https://csrc.nist.gov/pubs/sp/800/226/final) (accessed 2026-09-20) | Official publication page and publication text access | DP implementation hazards, scope of guarantees and complete-system consideration. |
| N02 | [NIST SDNist Synthetic Data Report Tool](https://www.nist.gov/services-resources/software/sdnist-synthetic-data-report-tool) (accessed 2026-09-20) | Official software description screened | Independent evaluation and reporting reference; not run locally. |
| D01 | [UCI Bank Marketing](https://archive.ics.uci.edu/dataset/222/bank+marketing) (accessed 2026-09-20) | Primary description and original CSV download | Task definition, provenance, attribution and license. |
| D02 | [UCI Student Performance](https://archive.ics.uci.edu/dataset/320/student+performance) (accessed 2026-09-20) | Primary description and original CSV download | Subject subsets, earlier/final grades and use-case limitation. |
| D03 | [UCI Wine Quality](https://archive.ics.uci.edu/dataset/186/wine+quality) (accessed 2026-09-20) | Primary description and original CSV download | Physicochemical features, outcome and attribution. |
| D04 | [SmartNoise Synth documentation](https://docs.smartnoise.org/synth/index.html) (accessed 2026-09-20) | Official fit/sample and transformation documentation | Preprocessing budget and model-specific domain requirements; version check still required. |

## Other discovery material

The user-provided ODSC [nine-tool article](https://odsc.medium.com/9-open-source-tools-to-generate-synthetic-data-b642cb10dd9a) and two GPT reviews supplied starting hypotheses. They are not used as authority for architecture, privacy or licensing. A 2025 [comparative survey](https://arxiv.org/abs/2507.11590) was screened for search breadth, but conclusions here are linked to original work and implementation evidence.

## Citation and evidence use

Published performance belongs to the cited paper, not this project. Local results have separate raw logs. An abstract-only entry does not mean the whole paper was critically replicated. Repository snapshots describe HEAD on the access date; executed wheels have their own exact versions. No unverifiable author, venue or DOI is filled in for an entry where it was not checked.

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
