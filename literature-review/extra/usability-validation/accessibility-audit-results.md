# Accessibility audit results

Date: 21 September 2026

Status: **automated audit complete; Orca event-path smoke complete; human screen-reader audit pending**.

## Automated browser audit

axe-core 4.10.3 and Chrome's full accessibility tree were captured for seven application states:

1. start screen;
2. guided editor;
3. recoverable invalid-JSON error;
4. single-table evidence report;
5. relational guided editor;
6. relational evidence report with assumptions expanded;
7. uploaded-data review with a suggested temporal fix.

Result: **zero axe violations**. Each screen has one `color-contrast` rule marked incomplete rather than failed. Its targets are custom controls or decorative symbols for which axe could not determine the effective background. Each meaningful symbol has adjacent text or an accessible name; decorative arrows and status marks are `aria-hidden`. The underlying text/action colour tokens passed the existing light/dark contrast measurement (4.5:1), and field boundaries passed 3:1. This manual disposition applies only to the listed targets and is recorded in the machine report.

The browser accessibility trees contain named main/navigation landmarks, headings, buttons, links, form controls, alerts, tables, regions and disclosures. The machine-readable evidence is at `platform/frontend/tests/artifacts/accessibility/automated-audit.json`.

## Orca event-path smoke

Orca 46.1 was run against headful Google Chrome with renderer accessibility forced. A programmatic keyboard/focus journey reached the start screen, design screen, invalid JSON error, generation and report download.

The actual Orca debug trace included these outputs:

- “Finished loading Attest Synth …”
- “main content”
- “Specification JSON entry {broken”
- “Unsaved changes — apply before generating”
- “Check these details” followed by the JSON syntax error
- “Step 03 · Create your records”
- “Preparing your evidence report…”

This trace found that the lazy-loaded report title was not reliably announced after the loading message. The report now moves programmatic focus to its level-one heading when it mounts; the automated audit asserts that this focus transition occurs. Changing the selected result table also updates a concise live status instead of requiring the user to infer that the following content changed. A human must still judge the resulting speech in the protocol run.

The event-path run is recorded at `platform/frontend/tests/artifacts/accessibility/orca-event-smoke.json`. The debug log itself stays in `/tmp` because it also records unrelated desktop accessibility events and is not suitable as a repository artifact.

## What remains

This is not a completed screen-reader audit. The [human protocol](screen-reader-audit.md) still needs a person to complete all 20 rows and judge reading order, verbosity, context, recovery and comprehension from speech. The user-study [results summary](results-summary.md) remains `not started`; no participant evidence has been invented.

Release status for accessibility: **not yet assessed for an institutional pilot**.
