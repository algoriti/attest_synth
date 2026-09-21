# Screen-reader audit protocol

Status: **human run pending**. Orca 46.1 is installed in the current environment and Chrome exposes an AT-SPI application, but a person must listen to, navigate and judge the output. Automated accessibility-tree evidence is complementary and cannot change this status.

Primary combination: Orca 46.1 with Google Chrome on Linux. Repeat critical tasks with NVDA + Chrome on Windows or VoiceOver + Safari on macOS before an institutional pilot if those combinations reflect intended users.

## Preparation

1. Build and run the app locally. Start with a fresh browser profile and 100% zoom.
2. Start Orca before opening the app. Leave normal verbosity enabled and record the Orca version.
3. Turn off the monitor for the core run, or ask the tester not to rely on it. Keep a facilitator available for safety and note every intervention.
4. Use fabricated data only. Do not run the hosted assistant with private content.

## Complete audit journey

| Step | Action | Expected information or behaviour | Result |
|---|---|---|---|
| 1 | Open the app and read from the top | Product name, four-step workflow, one level-one heading and introductory text are announced in a sensible order | pending |
| 2 | Use the skip link | Focus moves to main content; repeated header controls are bypassed | pending |
| 3 | Navigate by headings and landmarks | Header/navigation/main structure and section headings provide a useful outline without skipped or misleading levels | pending |
| 4 | Navigate by buttons | Starting paths, five templates, theme control and assistant action have unique, meaningful names; disabled state is announced | pending |
| 5 | Operate upload using keyboard | Upload control is announced as a button and opens a file chooser with Enter/Space | pending |
| 6 | Create a blank dataset | New screen title is announced or focus moves predictably to main; current workflow step is available | pending |
| 7 | Open the guided editor | Expanded state is announced; dataset, purpose and protected-entity controls have labels | pending |
| 8 | Navigate columns and rules | Each column disclosure announces name/type/role; inputs and select values have adequate context | pending |
| 9 | Add a column and leave edits unapplied | Status conveys unapplied edits; generation is disabled and its explanation is discoverable | pending |
| 10 | Try to leave, then cancel | Warning dialog is announced; cancelling returns to a predictable point without losing the draft | pending |
| 11 | Enter invalid advanced JSON | Error is announced without searching; message identifies the problem and focus can reach the editor/recovery action | pending |
| 12 | Recover and validate | Error no longer persists; successful state and next action are understandable | pending |
| 13 | Generate | Starting/running/completed changes are announced without repeated or overwhelming speech | pending |
| 14 | Read evidence by headings | Overall structural status, four headline measures, privacy limitation and check categories are understandable in reading order | pending |
| 15 | Navigate result-table controls | Selected state and row counts are announced; changing a table updates the following content predictably | pending |
| 16 | Read data and constraint tables | Captions/region names, headers and cell relationships are usable; horizontally scrollable regions are identifiable | pending |
| 17 | Expand checks and assumptions | Disclosure name, count and expanded/collapsed state are announced | pending |
| 18 | Download CSV/report/specification | Links are distinct, have file-purpose names and activate with Enter | pending |
| 19 | Run the relational template | Relationship/cardinality evidence and open assumptions remain understandable without visual layout | pending |
| 20 | Increase browser zoom to 200% | Reading order, focus and controls remain usable without loss of information | pending |

For every failure, record the exact spoken output, focused element, keystroke, expected result, actual result and whether the user could recover. A screenshot alone is insufficient evidence for a screen-reader issue.

## Completion criteria

The human audit is complete only when every row has a result and all blocker/high findings have an owner. “Pass” means the tester understood and completed the step from speech and keyboard input, not merely that an accessible name existed in the browser tree.

Run the automated companion from `platform/frontend`:

```bash
npm run test:a11y
```

Its report is written to `platform/frontend/tests/artifacts/accessibility/automated-audit.json`. Review all `incomplete` checks manually; zero automated violations is not a screen-reader pass.
