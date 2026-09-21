# Nontechnical participant session

Target participant: someone comfortable with ordinary web forms who does not routinely edit code, JSON or database schemas.

## Setup

- Start on the Attest Synth start screen in a fresh browser session.
- Use a desktop viewport around 1366×768 or larger at the participant's usual zoom.
- Do not describe the location of controls. Read only the task and neutral prompts below.
- Ask permission before audio, video or screen recording. Do not collect sensitive source data.

## Scenario shown to the participant

> You need sample data to test a small shop application. Create 50 products. Every product needs a new unique ID, a product name, a category chosen from `Books`, `Office`, and `Electronics`, a price between 5 and 200, and an in-stock value that is either true or false. Generate the data, check whether it passed its rules, download it, and tell us whether this report proves that the data is private.

## Tasks and observable success

| Task | Success without facilitator instruction | Critical? |
|---|---|---:|
| Choose a starting path | Opens the guided workflow without choosing upload or advanced JSON accidentally | yes |
| Name and size the dataset | Sets an understandable dataset name and 50 rows | yes |
| Define the columns | Creates the five requested columns with suitable types and value rules | yes |
| Correct a mistake | Changes one value or name after noticing it, without losing other work | no |
| Apply the design | Understands that edits must be applied before generation | yes |
| Generate | Starts generation and recognizes when it finishes | yes |
| Read the evidence | Correctly states whether structural checks passed and identifies at least one limitation | yes |
| Interpret privacy | Answers that the report does **not** prove privacy | yes |
| Download | Downloads the CSV | yes |

Start timing when the scenario is handed over. Stop at the successful download and explanation. Record wrong turns and self-corrections rather than offering immediate help.

## Neutral facilitator prompts

Use these only after 30 seconds without progress:

- “What would you expect to do next?”
- “What information on this screen seems relevant?”
- “Please continue as you normally would.”

If the participant still cannot proceed, record an intervention and provide the smallest instruction needed. Do not turn the session into a demonstration.

## Post-task questions

1. On a 1–7 scale, how easy or difficult was the task?
2. What did “apply and validate” mean to you?
3. What would you trust this generated dataset to be used for?
4. What would you **not** trust it to be used for?
5. Which words or controls were confusing?
6. If you returned next week, where would you start?
