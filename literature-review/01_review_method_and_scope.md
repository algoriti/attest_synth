# Review method and scope

Prepared 20 September 2026 for a general-purpose synthetic-data platform PoC.

## Project question

Which existing tools and methods can we reuse to help technical and nontechnical users create synthetic data for different projects, with explicit evidence about validity, usefulness, and privacy?

Healthcare is one possible domain. Banking, education, product quality, retail, government administration, manufacturing, and sensors are also relevant. The architecture should support several generation methods; no reviewed package is assumed to solve every modality or application.

## What this review is—and is not

This is an extensive, targeted engineering literature review with a reproducible exploratory benchmark. It is not a preregistered systematic review, exhaustive census, independent security audit, or production-readiness certification. No PRISMA counts or systematic-search completeness are claimed.

The two user-provided GPT discussions were treated as hypotheses and discovery material, not as evidence. The ODSC article was a starting list, not technical authority. Original papers, official documentation, repository files, actual licenses and package metadata were used to check claims.

## Search and selection

Searches covered original work and implementations for CTGAN/TVAE, Bayesian synthesis, sequential conditional models, copulas, adversarial random forests, differential privacy, diffusion, LLM-based synthesis, relational synthesis, time series, simulation and evaluation. Targeted queries included:

- `Modeling Tabular data using Conditional GAN 2019`
- `AIM Adaptive and Iterative Mechanism Differentially Private Synthetic Data`
- `synthpop Bespoke Creation Synthetic Data R 2016`
- `Adversarial Random Forests density estimation generative modeling`
- `TabDDPM modelling tabular data diffusion models`
- `Language Models are Realistic Tabular Data Generators`
- `REaLTabFormer generating realistic relational tabular data`
- `Time-series Generative Adversarial Networks`
- `synthetic tabular data benchmark 2025 TabSyn`
- `NIST synthetic data evaluation SDNist`

Discovery used the web search engine and direct publisher/repository URLs. Papers were selected for a distinctive method, practical reuse, or a finding that changes a design decision. Newer 2025–2026 work was screened to avoid treating GANs as the complete landscape. Abstract-only screening is identified in the source register; it supports the stated narrow finding, not detailed replication claims. Repository searches captured 14 versioned README/license pairs and eight successful source-file downloads. One additional REaLTabFormer source path returned 404 and is recorded rather than interpreted as absent functionality.

Inclusion: original method/evaluation work; official software documentation; inspectable implementation; relevance to a platform capability. Proprietary-only services, advertising claims, unrelated uses of the word “synthetic”, and unsupported performance rankings were excluded from recommendations. Source-available BSL packages were retained as comparators, clearly distinguished from permissively licensed dependencies.

## Evidence labels

| Label | Meaning |
|---|---|
| Published | A finding reported by the cited authors under their experimental conditions |
| Documented | An upstream capability or limitation described by maintainers |
| Inspected | Behavior identified in a captured source or license file |
| Executed | Observed in this review's scripts, inputs and environment |
| Proposed | Our engineering recommendation or experiment still to run |

All recommendations combine evidence and engineering judgment. They are not silently presented as findings of the cited papers.

## Experimental coverage

Executed: public single-table data in banking, education and wine quality; three seeds; three installed synthesis libraries plus independent sampling and copying controls; two downstream predictors; schema-only examples in retail, education and sensors.

Not executed: Synthcity, neural training, SmartNoise DP synthesis, membership/attribute-inference attacks, relational model training, learned time series, LLM calls, usability studies, image/audio/text generation, production deployment or private-data processing. These are literature/source-reviewed or explicitly future work. We chose a bounded CPU experiment, not a claim that untested tools failed to install.

## Traceability and limitations

- [Source register](07_sources.md): sources and what each supports.
- [Repository manifest](evidence/repository_manifest.json): exact commits, dates, hashes and license links. Default-branch commit date and repository push date are different signals; neither alone proves maintenance quality.
- [Source manifest](evidence/source_manifest.json): successfully captured source and failed retrieval.
- [PyPI metadata](evidence/pypi_metadata.json): released package versions/dependencies, which may differ from repository HEAD.
- [Dataset manifest](benchmarks/data/manifest.json): primary UCI URLs and SHA256 checksums.
- [Experiment environment](benchmarks/results/environment.json): exact direct versions and run timestamps.

The initial UCI download was slow. Mirror acquisition was explored, including rejection of an 11,162-row altered banking file. The final inputs were re-fetched from UCI and verified against the primary manifest before benchmarking. The mirror script is acquisition history, not the source of the final results.

The review is strongest on structured data and practical integration. Image/text/audio/graph capabilities need separate, deeper reviews before implementation. No nontechnical user study or institution-specific utility claim is supported by the work here.

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
