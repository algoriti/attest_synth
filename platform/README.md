# Synthetic Data Platform — local proof of concept

A general-purpose tabular synthetic-data workbench. Create a dataset through guided controls, import a JSON specification, describe a scenario to the optional Groq assistant, or upload approved records. Review the specification, generate data, and inspect evidence before downloading it.

The platform owns the specification, validation, derived values, relationship checks and evaluation. Engines supply base values. Employee attendance is one example alongside retail, education and sensor examples; the product is not limited to healthcare or employee data.

## Run locally

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r platform/backend/requirements.txt
npm --prefix platform/frontend ci
npm --prefix platform/frontend run build
cd platform/backend
../../.venv/bin/python -m uvicorn synthetic_platform.api:app --host 127.0.0.1 --port 8770
```

Open `http://127.0.0.1:8770`. FastAPI serves the built frontend. For frontend development, run `npm run dev` from `platform/frontend`; its client uses localhost port 8770.

## Two authoring workflows

**Guided:** choose “Create your own dataset” or an example, open “Edit tables, columns and relationships,” and declare the records you need. Add columns, value rules, formulas and links. Apply and validate changes before generating. Unsaved edits block generation.

**Technical:** import a specification JSON file, or switch the editor to Advanced JSON. Invalid edits remain in the editor with an explanation. Export the specification to keep or share the recipe. A completed job also provides its resolved specification, including the actual requested row count.

Uploads propose column roles and candidate formulas. Formula matches display comparable-row counts and exceptions. “Accept rule” records a scenario decision; “Learn instead” rejects the deterministic formula. Reprofiling with another timezone explicitly warns that it replaces column edits and decisions. Temporal rewrites can make unsupported timestamp columns learnable, but currently collapse dates into a reference week; use the stated limitation when deciding whether that transformation fits the task.

## Groq assistant

The default is **`openai/gpt-oss-120b` with high reasoning effort**, selected from [Groq’s production model documentation](https://console.groq.com/docs/model/openai/gpt-oss-120b) and [reasoning documentation](https://console.groq.com/docs/reasoning), checked on 21 September 2026. This is Groq hosting the model, not xAI/Grok.

Copy `platform/backend/.env.example` to `platform/backend/.env` if the local file does not already exist, then set:

```dotenv
GROQ_API_KEY=your_key_here
SYNTHETIC_LLM_BASE_URL=https://api.groq.com/openai/v1
SYNTHETIC_LLM_MODEL=openai/gpt-oss-120b
SYNTHETIC_LLM_REASONING=high
```

The backend reads this file without executing shell commands. Environment variables override file settings. `.env` is excluded from Git; never place the key in a frontend `VITE_` variable. The status endpoint reports configuration availability, not credentials.

The assistant sends the typed user scenario and the platform’s JSON schema only. It does not read uploads, previews or source records. Its output is a proposal: privacy, engine and semantic validation run before the UI accepts it. All model-proposed provenance remains unconfirmed. One additional correction request is allowed for semantic errors; invalid output otherwise produces a recoverable error. Generation still requires the user’s review action. A provider call can take up to 120 seconds; a correction can take another call.

The schema-only hosted smoke check is in `backend/benchmarks/check_hosted_assistant.py`. It has successfully obtained a Groq proposal and generated ten structurally valid product records. This verifies integration, not the quality of every future model proposal.

## What is implemented

| Area | Supported behaviour |
|---|---|
| Schema-only generation | Rules/Faker, identifiers, constants, nullable fields and explicit formulas |
| Learned generation | ARF for one table; independent-column baseline; internal engine column-name mapping |
| Relationships | Parent-first generation, one-to-many, one-to-one, up to two parents per child, bounded junction allocation, declared compound uniqueness |
| Optional links | Explicit null fraction for single-parent children; unsupported optional-junction combinations are rejected |
| Aggregates | Count, sum, mean, min and max of child records onto parent columns; empty-group policy and denominator reported |
| Cross-table checks | Numeric and temporal comparisons through declared parent-child relationships; explicit missing-value policy |
| Evidence | Final schema/PK/FK/cardinality checks, explicit constraints, repair counts, assumptions and requested-check status |
| Utility | Generator fits training records only; random, entity-group or time holdouts; binary AP/AUC, multiclass balanced accuracy and regression MAE/R² |
| Reproduction | Resolved specification, source and artifact hashes, dependency versions and seed |
| UI | Guided editor, advanced JSON, import/export, proposal decisions, result-table navigation, retry on polling failures |

The junction solver supports at most 50,000 candidate parent pairs and a ten-second solve limit. Each table is capped at 200,000 rows; uploads at 20 MB and 200 columns; specifications at 20 tables. At most two generation jobs run concurrently. Infeasible rules produce a clear failure; this engine does not relax them silently.

Aggregate columns use role `aggregate` and are declared in the specification’s `aggregates` list. Their group is the parent key. Counts count all linked rows; other operations ignore null source values and use the stated empty-group value. Chained aggregates and formulas depending on aggregate outputs are not supported. Employee-month/period summaries require additional grouping/period design; parent totals alone do not implement that feature.

Numeric derived results are not silently clipped or rounded. Use `clip` or `round` explicitly in the expression if that is the intended rule. Final structural failures appear in the top-level report; a completed job does not necessarily mean its output passed all checks.

## Evaluation limits

Generator fitting never sees the held-out partition. However, the upload profiler and a user may have inspected the full upload before choosing the schema or accepting formulas. Those choices make the result exploratory; a rigorous final experiment needs training-only discovery or a genuinely untouched external test set. The included platform benchmark uses fixed schemas without full-dataset rule discovery.

Seeded rules are reproducible. Learned-engine reproducibility must be verified with artifact hashes; a seed alone is not a guarantee. Utility and exact-row-match diagnostics are not privacy guarantees. None of these engines implements differential privacy.

The attendance export contains missing clock-outs and unusually long sessions. No institutional schedule, lateness policy, overtime definition or productivity labels have been confirmed. The sample marks its cutoff and standard-day values as assumptions. Raw attendance upload is not certified as a faithful longitudinal workflow; do not infer absence or employee performance from this file alone.

## Verification

From the repository root:

```bash
.venv/bin/python -m pytest platform/backend/tests -q
npm --prefix platform/frontend run build
.venv/bin/python platform/backend/benchmarks/run_platform_benchmark.py
```

With the built app running on port 8772:

```bash
cd platform/frontend
npm run test:workflow
```

The browser script uses installed Google Chrome and Playwright; `PLATFORM_URL` can override the test URL. It checks guided creation, unsaved-edit blocking, invalid JSON, relational examples, CSV downloads, a temporal rewrite with ARF, and mobile layout. Screenshots and results are under `frontend/tests/artifacts`.

Run `npm run test:ui` from `platform/frontend` for targeted keyboard, draft-preservation, theme-contrast and responsive-layout checks. The [interface review](../literature-review/extra/platform_ui_ux_review.md) explains the design changes and links the before/after screenshots. A full screen-reader audit and usability sessions with representative users remain pending.

Run `npm run test:a11y` for axe-core checks and accessibility-tree evidence across the start screen, editor, error recovery and single/relational reports. The [validation kit](../literature-review/extra/usability-validation/README.md) contains the nontechnical, technical and 20-step human screen-reader protocols. Automated evidence cannot replace participant or human assistive-technology results.

The [platform benchmark](backend/benchmarks/README.md) contains 27 trials across public banking, education and wine data with three seeds. The copying control exists only inside that benchmark. The original literature-review benchmark is a separate experiment.

## Scope before a shared pilot

This remains a local PoC. Upload/job metadata is in memory and artifacts are stored on disk. Authentication, per-user ownership, durable workers, cancellation, retention/cleanup and an institutional disclosure process are not implemented. A database alone would not complete those controls. Cross-origin access is restricted to the local development frontend.

Native learned relational synthesis, entity-time behaviour models and a validated employee-period performance simulation remain separate experiments. The [prioritized roadmap](../literature-review/extra/platform_poc_roadmap_and_todo.md) tracks completed work and remaining decisions.
