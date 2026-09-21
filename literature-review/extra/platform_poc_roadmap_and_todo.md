# PoC roadmap and implementation checklist

This is the live implementation checklist after the [implementation review](platform_implementation_review_2026-09-21.md). Implementation is authorized and underway. Checked items have implementation and regression coverage; scoped limitations are recorded below. The platform remains general-purpose; attendance is a demanding example, not the scope of the product.

## Milestone 1 — Make the evidence trustworthy

- [x] R1: constrain table/artifact names and enforce storage containment. Acceptance: traversal and absolute-name specs cannot write outside their job directory.
- [x] R2: split real records before generator fitting and feature materialization. An instrumented engine sees zero held-out rows; source/split hashes and random/group/time strategies are reported.
- [ ] Move interactive upload profiling and policy discovery into training-only partitions for confirmatory utility studies. Current upload scores remain exploratory if the schema was chosen after inspecting the full source; the fixed-schema benchmark avoids that discovery step.
- [x] R3: implement final schema, PK, FK, required-nullability, row-count and cardinality checks. Acceptance: each invalid probe reports failure in the top-level status and UI.
- [x] R4: remove silent formula-changing repairs or express them explicitly. Acceptance: formula outputs and downstream dependencies agree; every repair is counted.
- [x] R6: fix temporal round-trip semantics. Acceptance: timezone, midnight, missing timestamp and duration consistency tests pass.
- [x] R9: isolate engine-internal column names with a reversible mapping. Acceptance: learned datasets with columns such as `value`, `tree` and `nodeid` complete without collisions and export the original schema.
- [x] Validate evaluation targets and mark each requested check as passed, failed, skipped or unsupported. Acceptance: multiclass/unsupported temporal requests cannot silently receive a misleading binary result.
- [x] Record platform/engine dependency versions, source hash, actual row override, full resolved spec and artifact hashes. Acceptance: an export contains enough information to rerun the same request; verify deterministic engines before claiming reproducibility.

Exit: existing tests plus the new regression cases pass. A green report means every applicable required check passed. This milestone comes before showcasing ML utility.

## Milestone 2 — Finish the relational rules contract

- [x] Separate PK, FK, compound business key and ordinary attribute roles; prohibit derivations that overwrite finalized relationship keys.
- [x] Enforce cardinality across every parent, not only the first relationship. Reject infeasible combinations clearly.
- [x] Define optional-link null probability explicitly; remove the hidden 2% assumption. Support or clearly reject zero-child outputs.
- [x] Support declared compound uniqueness for two-parent junctions; repeated pairs remain allowed when no compound key is declared.
- [ ] Model assignment episodes and time validity explicitly before claiming longitudinal assignment support.
- [x] Check numeric and temporal bounds across a declared relationship, with explicit fail/skip handling for missing values. These checks detect violations; they do not solve arbitrary temporal constraint systems.
- [x] Add count/sum/mean/min/max child-to-parent aggregates with explicit empty-group handling and reported denominators.
- [ ] Extend grouping to employee-period outputs and chained summaries. Current parent totals are not monthly behaviour modelling.
- [x] Align engine capability labels and documentation with implemented operations.

Exit: employee, retail and education fixtures each exercise one-to-many and junction relationships; all supported key, count, compound and temporal rules pass across multiple seeds. Invalid specifications fail before expensive generation where possible.

## Milestone 3 — Complete the nontechnical workflow

- [x] Guided schema creation and editing, plus validated JSON import/export.
- [x] Relationship editor showing parents, children, key types, optionality and counts.
- [x] Candidate-rule cards with match numerator/denominator, exceptions, and accept/edit/reject controls.
- [x] Correct the sample attendance policy provenance; distinguish observed data summaries from assumed scenario rules.
- [x] Let users choose purpose, protected entity, timezone and supported evaluation target through the UI.
- [x] Show requested versus performed checks and separate structural validity, statistical similarity, utility and privacy statements.
- [x] Add job polling timeout/retry and recoverable failure messages; retain or explicitly reset edits when reprofiling.
- [x] Improve long report navigation with summary and table tabs; browser checks verify table navigation and no page-wide horizontal overflow at a 390px viewport.
- [x] Refine typography, card hierarchy, source paths, form controls, editor grouping, theme contrast and mobile layout. Preserve hidden editor drafts and distinguish unapplied edits from validation failures. See the [UI review](platform_ui_ux_review.md).
- [x] Complete automated keyboard coverage across creation, editing, validation, generation and downloads; axe-core reports zero violations across seven principal states, and the Chrome accessibility tree is captured. Orca event tracing identified and led to a report-focus fix.
- [ ] Complete the 20-step human screen-reader protocol with a routine screen-reader user. Automated checks and Orca event traces do not establish speech comprehension.
- [ ] Run the prepared task sessions with at least three nontechnical and three technical participants, then prioritize observed findings. Participant status remains `not_started`.

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

- [x] Re-run an engine comparison through the actual platform on at least three domains, with repeated seeds and fixed, leakage-free splits.
- [x] Compare independent baseline and ARF on three public domains, with a real-training reference and a copying control registered only inside the benchmark. Rules are verified separately using three relational domain fixtures.
- [x] Record structural checks, repairs, marginal/numeric-dependency fidelity, task utility, runtime and process peak RSS in 27 benchmark trials. Relational fixture tests check keys, cardinalities and aggregates separately.
- [ ] Add learned join-distribution and longitudinal utility benchmarks after introducing those models.
- [ ] For entity/event datasets, compare grouped and temporal tasks appropriate to the intended use; report variability and limitations.
- [x] Integrate Groq `openai/gpt-oss-120b` with high reasoning, backend-only credentials, validation and one bounded correction attempt. Send only the user scenario and platform specification format; never uploaded records. Live proposal → validation → ten-row generation passed.
- [ ] Evaluate hybrid/native relational engines as separate experiments with documented license/version and measured value over the rules baseline.

Exit: recommendations are supported by platform-run measurements. No single engine is labelled best for every domain or every data modality.

## Before a shared institutional pilot

- [x] Bound upload size (20 MB), tables/columns (20/200), output rows (200,000/table), concurrent generation jobs (2), junction candidate pairs (50,000) and solver time (10 seconds).
- [ ] Add worker cancellation and global generation timeouts. The UI reconnect timeout does not cancel a worker.
- [ ] Add authenticated ownership and access checks for uploads, jobs and downloads.
- [ ] Add durable job metadata, artifact lifecycle/retention and controlled cleanup; a database alone does not replace the worker lifecycle or artifact storage design.
- [ ] Review API errors and logs so previews and tracebacks do not expose records across users.
- [ ] Define a separate privacy evaluation/release process if generation uses private records. The present engines provide no formal DP guarantee.

These are deployment criteria, not a requirement to build an enterprise system before completing the local PoC.

## Implementation evidence and remaining scope

- [Platform usage and implementation limits](../../platform/README.md).
- [27-run platform benchmark](../../platform/backend/benchmarks/README.md): public banking, education and wine data, three seeds, all trials completed and structural checks passed. This is separate from the earlier literature-review benchmark.
- Final backend verification: **110 tests passed**, with one Starlette test-client dependency deprecation warning. Regression tests include `platform/backend/tests/test_review_regressions.py`; existing platform tests are retained and updated where the explicit-holdout evaluation contract changed.
- Frontend production build passed. Report/chart code now loads on demand: the initial JavaScript bundle is about 271 KB before compression, with a separate 374 KB report bundle. The previous bundle-size advisory is resolved.
- Frontend lint completed with zero errors and seven warnings (Fast Refresh export organization and state synchronization effects). These warnings remain maintenance work, not a completed accessibility audit.
- Final browser rerun passed all six workflow checks with zero page errors after correcting polling to reset consecutive connection failures on a successful response. `git diff --check` also passed.
- Browser checks and screenshots: `platform/frontend/tests/artifacts`; guided creation, imported relational examples, downloads, temporal fixes and mobile layout.
- UI refinement evidence: `platform/frontend/tests/artifacts/ui-review`; 19 targeted checks cover keyboard actions, draft preservation, theme-token contrast and 320/390/768/1440px layouts. This does not complete the full accessibility or participant usability audit.
- [Usability and screen-reader validation kit](usability-validation/README.md): real-user tasks, observation sheet, decision rules and a 20-step Orca protocol. Automated audit evidence covers seven screens with zero axe violations; axe's per-screen incomplete contrast checks have the documented manual disposition.
- Groq integration check: `platform/backend/benchmarks/results/hosted_assistant_check.json`. No credentials or uploaded records are included.

The local PoC supports at most two parents per child and parent-key aggregation. Native learned relational synthesis, employee-period simulation, confirmed attendance policies and a multi-user institutional deployment are still open work. A schema-only fixture or a successful model call does not establish those capabilities.
