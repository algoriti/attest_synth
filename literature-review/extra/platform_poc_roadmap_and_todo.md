# PoC roadmap and implementation checklist

This is a proposed work queue after the [implementation review](platform_implementation_review_2026-09-21.md). Implementation is not started by this document. The platform remains general-purpose; attendance is a demanding example, not the scope of the product.

## Milestone 1 — Make the evidence trustworthy

- [ ] R1: constrain table/artifact names and enforce storage containment. Acceptance: traversal and absolute-name specs cannot write outside their job directory.
- [ ] R2: split real records before synthesis and fitted preprocessing. Acceptance: an instrumented engine sees zero held-out rows; source/split hashes and split strategy appear in the report.
- [ ] R3: implement final schema, PK, FK, required-nullability, row-count and cardinality checks. Acceptance: each invalid probe reports failure in the top-level status and UI.
- [ ] R4: remove silent formula-changing repairs or express them explicitly. Acceptance: formula outputs and downstream dependencies agree; every repair is counted.
- [ ] R6: fix temporal round-trip semantics. Acceptance: timezone, midnight, missing timestamp and duration consistency tests pass.
- [ ] R9: isolate engine-internal column names with a reversible mapping. Acceptance: learned datasets with columns such as `value`, `tree` and `nodeid` complete without collisions and export the original schema.
- [ ] Validate evaluation targets and mark each requested check as passed, failed, skipped or unsupported. Acceptance: multiclass/unsupported temporal requests cannot silently receive a misleading binary result.
- [ ] Record platform/engine dependency versions, source hash, actual row override, full resolved spec and artifact hashes. Acceptance: an export contains enough information to rerun the same request; verify deterministic engines before claiming reproducibility.

Exit: existing tests plus the new regression cases pass. A green report means every applicable required check passed. This milestone comes before showcasing ML utility.

## Milestone 2 — Finish the relational rules contract

- [ ] Separate PK, FK, compound business key and ordinary attribute roles; prohibit derivations that overwrite finalized relationship keys.
- [ ] Enforce cardinality across every parent, not only the first relationship. Reject infeasible combinations clearly.
- [ ] Define optional-link null probability explicitly; remove the hidden 2% assumption. Support or clearly reject zero-child outputs.
- [ ] Define duplicate junction semantics; support compound uniqueness and optional assignment episodes.
- [ ] Make cross-table date/interval checks explicit, including assignment and project boundaries.
- [ ] Add post-generation aggregate operations with stated grouping grain, denominators and missing-value handling.
- [ ] Align engine capability labels and documentation with implemented operations.

Exit: employee, retail and education fixtures each exercise one-to-many and junction relationships; all supported key, count, compound and temporal rules pass across multiple seeds. Invalid specifications fail before expensive generation where possible.

## Milestone 3 — Complete the nontechnical workflow

- [ ] Guided schema creation and editing, plus validated JSON import/export.
- [ ] Relationship editor showing parents, children, key types, optionality and counts.
- [ ] Candidate-rule cards with match numerator/denominator, exceptions, and accept/edit/reject controls.
- [ ] Correct the sample attendance policy provenance; distinguish observed data summaries from assumed scenario rules.
- [ ] Let users choose purpose, protected entity, timezone and supported evaluation target through the UI.
- [ ] Show requested versus performed checks and separate structural validity, statistical similarity, utility and privacy statements.
- [ ] Add job polling timeout/retry and recoverable failure messages; retain or explicitly reset edits when reprofiling.
- [ ] Improve long report navigation with summary and table tabs; verify keyboard operation and mobile scrolling.

Exit: a new user can create and validate a small retail or education relational dataset without editing Python, and can explain which parts were learned, assumed or computed.

## Milestone 4 — Validate the attendance use case honestly

- [ ] Confirm timezone and meanings of late status, extra hours, active/open session and sign-in date with the data owner, or leave them unresolved.
- [ ] Specify treatment of the 156 missing clock-outs and 3,151 durations above 24 hours; retain raw-source counts and exclusion reasons.
- [ ] Define the prediction question before selecting entity/time splits and evaluation targets.
- [ ] Preserve synthetic employee identity consistently across repeated events; distinguish row IDs from entity IDs.
- [ ] Generate schedules only as explicit assumptions unless actual schedule records are available.
- [ ] Generate tasks/projects/reports as declared scenarios; compute employee-period summaries from the generated events.
- [ ] Verify raw-upload → review → accepted transformation → generation → downloadable evidence in the UI, separately from the CLI feature-engineered demo.

Exit: the demonstration supports attendance-pattern or software-testing claims appropriate to its evidence. It makes no empirical productivity or absence claim from unsupported fields.

## Milestone 5 — Benchmark the platform and then add assistance

- [ ] Re-run an engine comparison through the actual platform on at least three domains, with repeated seeds and fixed, leakage-free splits.
- [ ] Compare rules, independent baseline and ARF where each is applicable; include real-training utility reference and an explicitly labelled copying control only in the benchmark.
- [ ] Measure constraints and repairs, distribution/dependency fidelity, task utility, relational joins/cardinalities, runtime and memory separately.
- [ ] For entity/event datasets, compare grouped and temporal tasks appropriate to the intended use; report variability and limitations.
- [ ] Add an LLM specification assistant only after contract validation and proposal confirmation work. Give it schema/approved summaries by default, not raw sensitive records. Its output must pass the same validator and unsupported-capability checks.
- [ ] Evaluate hybrid/native relational engines as separate experiments with documented license/version and measured value over the rules baseline.

Exit: recommendations are supported by platform-run measurements. No single engine is labelled best for every domain or every data modality.

## Before a shared institutional pilot

- [ ] Bound upload sizes, table/column counts, output row counts and concurrent jobs; add cancellation and timeouts.
- [ ] Add authenticated ownership and access checks for uploads, jobs and downloads.
- [ ] Add durable job metadata, artifact lifecycle/retention and controlled cleanup; a database alone does not replace the worker lifecycle or artifact storage design.
- [ ] Review API errors and logs so previews and tracebacks do not expose records across users.
- [ ] Define a separate privacy evaluation/release process if generation uses private records. The present engines provide no formal DP guarantee.

These are deployment criteria, not a requirement to build an enterprise system before completing the local PoC.
