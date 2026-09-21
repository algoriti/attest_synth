# Attest Synth usability validation

This folder contains the materials for the next evidence-gathering stage. It deliberately separates three kinds of evidence:

1. **Participant evidence:** observed behaviour from real technical and nontechnical users.
2. **Human assistive-technology evidence:** a person completing the workflow with a screen reader.
3. **Automated evidence:** repeatable browser checks, axe-core results and the browser accessibility tree.

Automated or simulated results must never be entered as participant findings. The current participant-results file is marked `not_started` until real sessions occur.

## Minimum study

- Recruit at least three people who do not routinely write code and three people who work with schemas, data or software. None should have built this interface.
- Include at least one person who routinely uses a screen reader for the assistive-technology session. If that is not immediately possible, an experienced tester may run an expert audit, but label it as an expert audit rather than a user result.
- Run sessions individually. Allow 35–45 minutes. Do not teach the interface before the first task.
- Use fabricated scenarios and public fixtures only. Do not ask participants to upload employer, patient, student or customer records.
- Record the app version or Git commit, browser, viewport, assistive technology and any facilitator intervention.

## Files

- [Nontechnical session](nontechnical-session.md): create and assess a small product catalogue.
- [Technical session](technical-session.md): import, inspect, break, recover and generate a relational dataset.
- [Screen-reader audit](screen-reader-audit.md): a complete Orca + Chrome journey with expected announcements.
- [Accessibility results](accessibility-audit-results.md): automated and Orca event-path evidence, with the human audit kept pending.
- [Observation sheet](observation-sheet.md): one copy per participant.
- [Results summary](results-summary.md): aggregate only after sessions are completed.

## Decision rule

Do not declare the interface ready for a pilot merely because every participant eventually finishes. A release-blocking issue is any of the following:

- a participant cannot complete a critical task without facilitator instruction;
- a screen-reader user cannot identify the current step, understand an error, operate the editor, determine whether checks passed, or activate a download;
- two participants make the same material interpretation error about privacy, assumptions or the evidence report;
- data is lost without a clear warning;
- focus becomes trapped, hidden or moves unpredictably during a critical task.

Fix release-blocking findings and rerun the affected task with a new participant. Smaller findings should be ranked by frequency, impact and repair cost.
