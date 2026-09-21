# Attest Synth interface review and refinement

Reviewed 21 September 2026. Scope: start, schema review, guided and JSON editors, generation, evidence report, desktop/mobile layouts and both themes. This is an implementation review and browser verification, not a study with representative users.

## Review findings and changes

| Area | Finding in the earlier interface | Implemented refinement |
|---|---|---|
| First decision | Uploads, a long example list, AI and engine descriptions competed for attention. One source card stretched to the height of the examples in its neighbour. | Two balanced starting paths; templates in their own gallery; AI assistance in a separate section; engine comparison behind a disclosure. |
| Typography | The 20px page title was close to the 15px card titles. Labels and explanation text were small; textareas and inputs without an explicit type could retain browser defaults. | Locally served Lato, 28–38px page headings, 20px section titles, 15px body copy and 13px supporting text. Shared input and textarea styling. Monospace remains for technical values. |
| Visual hierarchy | Almost every element had the same white-card treatment and similar weight. | Teal primary action, quieter secondary actions, neutral surfaces, distinct section spacing and a subtle accent on the guided starting path. Status colours carry specific meanings. |
| Cards and spacing | Examples were stacked inside another card; headers mixed title and subtitle on one line. | Separate responsive template grid, title/subtitle hierarchy, consistent card padding and metadata placement. No decorative imagery competing with dataset tasks. |
| Language | Template names exposed underscores and engine terminology; controls displayed values such as `integer_range`. | Task-based template names and plain-language generation-rule choices. Exact schema names remain in technical views and exports. |
| Forms | Long editors had little grouping; it was hard to distinguish column sections. | Numbered, collapsible column sections, a visible guided/JSON selection and grouped apply/discard actions. Identifier sections start collapsed. |
| Draft safety | Hiding the editor unmounted its draft. Unapplied edits could show a rejected-specification message with zero errors. | Preserve drafts while hiding; separate unapplied edits from validation failures; disable generation-setting changes while a draft is pending; warn before leaving or reloading with unapplied edits. |
| Workflow orientation | The current step lacked an accessibility state; page changes left focus at the old control. | Named workflow navigation, `aria-current`, focus moved to main content after screen changes, skip link and a shortcut to generation settings. |
| Upload | The clickable upload `div` was not keyboard-operable. | Native upload button supporting keyboard and drag/drop, file type/size guidance and a busy state. |
| Feedback | Failures, limitations and pending changes were visually conflated. | Actionable validation wording, error alerts, status announcements and specific disabled-action explanations. The absence of a privacy guarantee remains visible as a limitation. |
| Evidence | Table selections were not visually distinct; download links contained nested buttons. Long constraint and assumption tables dominated mobile reports. | Selected-table styling, separate check tiles, semantic download links, stronger metric hierarchy. All-passed constraint details and assumption lists can be expanded; failing constraints remain expanded initially. Completed checks are not automatically styled as passed checks. |
| Responsive layout | Workflow labels disappeared on small screens and minimum grid widths could constrain layout. | Full step labels on a second navigation row; cards and forms reflow; wide previews scroll inside their own region. Mobile header is not sticky, preserving usable space and focus visibility. |
| Accessibility | Muted text and control boundaries needed explicit measurement. | Contrast checks for text, primary actions and status colours in both themes; stronger field boundaries, visible focus and reduced-motion support. |
| Loading | Chart/report code was loaded for the first screen. | Evidence report and chart code load on demand, with a visible loading status. Fonts are served locally with `font-display: swap`. |

## Design rules used

- Use a single main heading per screen. Section headings describe tasks; helper text explains consequences or the next step.
- Keep the next action more prominent than configuration details. Secondary disclosures retain advanced functionality without requiring a new user to understand it immediately.
- Use spacing to group related fields and distinguish sections. Use colour together with a label, never as the only status signal.
- Keep forms and downloads native HTML controls where possible. Large primary controls use a 44px minimum height; this does not imply every inline link or checkbox is 44px.
- Preserve the evidence distinctions: structural validity, learned similarity, prediction usefulness and privacy are separate claims.

The contrast checks use the [WCAG text-contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html): normal text needs at least 4.5:1. Larger targets and control spacing follow the intent of [WCAG target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), whose minimum is 24×24 CSS pixels with specified exceptions. Focus treatment and mobile header behaviour were informed by [focus-not-obscured guidance](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html). These references guide implementation; they are not evidence that the whole app conforms to WCAG.

## Verification and visual evidence

Run the built app on port 8772, then run from `platform/frontend`:

```bash
npm run test:workflow
npm run test:ui
```

`PLATFORM_URL` overrides the local URL. Tests use the installed Google Chrome executable and Playwright.

- [Targeted UX checks and contrast measurements](../../platform/frontend/tests/artifacts/ui-review/results.json)
- [Earlier start screen](../../platform/frontend/tests/artifacts/ui-review/before-source.png)
- [Refined desktop start](../../platform/frontend/tests/artifacts/ui-review/desktop-start.png)
- [Dark theme](../../platform/frontend/tests/artifacts/ui-review/dark-start.png)
- [Guided editor](../../platform/frontend/tests/artifacts/ui-review/desktop-editor.png)
- [Evidence report](../../platform/frontend/tests/artifacts/ui-review/desktop-report.png)
- [Mobile start](../../platform/frontend/tests/artifacts/ui-review/mobile-start.png)
- [Mobile editor](../../platform/frontend/tests/artifacts/ui-review/mobile-editor.png)
- [Mobile report](../../platform/frontend/tests/artifacts/ui-review/mobile-report.png)

The targeted suite checks page overflow at 320, 390, 768 and 1440px; light/dark token contrast; keyboard upload, creation, generation and download; draft preservation; navigation cancellation; focus after navigation; and selected report-table state. It does not use a real hosted assistant request or upload private records.

Verification: the production build, six existing workflow checks and 19 targeted UI checks passed with no browser page errors. Lint completes with seven existing warnings and no errors. Code splitting reduced initial JavaScript from approximately 644 KB to 271 KB before compression (about 83 KB gzip); report code is a separate approximately 374 KB chunk. This is a bundle-size measurement, not a measured improvement in user-perceived load time.

## Next validation with people

1. Ask a nontechnical participant to create a small order dataset, change a rule, generate it and explain the report's limitations. Record where they need help.
2. Ask a technical participant to import a relational specification, inspect relationships, correct invalid JSON and export the resolved result.
3. Perform a screen-reader and complete keyboard-only audit, including error recovery, all relationship controls and complex reports. Targeted keyboard automation does not replace this.
4. Check larger real-world schemas and longer names with users. Table search, bulk editing and richer relationship diagrams should follow observed needs.

No claim of universal ease of use or complete accessibility is made. Font assets are unmodified Lato files distributed with their OFL licence under `platform/frontend/public/fonts`; further transfer-size optimization is possible.
