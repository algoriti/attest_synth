# Technical participant session

Target participant: a developer, analyst, data engineer or researcher familiar with schemas or structured data. Prior knowledge of this codebase is excluded.

## Setup

- Start on the Attest Synth start screen in a fresh browser session.
- Provide `platform/backend/specs/retail_relational.json` as the approved public fixture.
- Do not describe the platform architecture before the participant completes the first task.

## Scenario shown to the participant

> Import the supplied retail specification. Determine how its three tables are related, find where order-line totals come from, and identify the uniqueness rule on the junction records. Introduce an invalid JSON edit, recover without reloading, generate the dataset, inspect relationship and constraint evidence, download the order-line data, and export or download the specification used to reproduce the job.

## Tasks and observable success

| Task | Success without facilitator instruction | Critical? |
|---|---|---:|
| Import | Imports the JSON specification and reaches the design review | yes |
| Explain structure | Identifies customers and products as parents of order lines | yes |
| Locate computation | Finds that `line_total` is computed rather than independently sampled | yes |
| Locate uniqueness | Finds the customer/product pair or declared compound uniqueness and explains its effect | yes |
| Use advanced mode | Opens JSON, introduces a syntax error and receives an actionable error | yes |
| Recover | Discards or corrects the bad edit without reloading or losing the valid specification | yes |
| Generate | Selects a valid engine and completes generation | yes |
| Read evidence | Distinguishes schema/constraint/cardinality status and recognizes open assumptions | yes |
| Export | Downloads `order_lines` and the resolved specification | yes |
| State limits | Does not claim learned relational fidelity or a privacy guarantee | yes |

## Follow-up probes

- “Where would you look if a relationship were infeasible?”
- “Which part is a generator result and which part is computed after generation?”
- “What evidence would you still need before using private institutional data?”
- “Which controls should be visible sooner, and which can stay under technical details?”

Record whether technical concepts are discoverable from the interface itself. Familiarity with JSON must not be counted as evidence that the guided workflow is clear.
