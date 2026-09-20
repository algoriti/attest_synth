# Synthetic Data PoC: Employee Behavioral Modeling and Relational Extension Review

## 1. Purpose of this note

This note consolidates the main conclusions from the recent PoC discussions around:

1. what the synthetic-data PoC is expected to prove;
2. how the supplied `Attendance.csv` can be used as a realistic employee-data demonstration;
3. how the dataset can be extended toward employee work-behavior and performance experimentation; and
4. why relational data support should become an explicit extension of the PoC rather than forcing all information into one flat table.

The goal is to keep the PoC general-purpose while using the employee-attendance scenario as one strong demonstration.

---

## 2. Current PoC definition

The PoC should demonstrate an **intelligent structured synthetic-data platform**, not only a script that produces fake rows.

A technical or nontechnical user should be able to:

- describe the dataset they need;
- define a schema manually;
- upload an approved source dataset;
- inspect and edit the inferred specification;
- choose or be guided toward a supported generation mode;
- generate synthetic data;
- validate the generated output;
- evaluate fidelity and task utility where applicable;
- preserve provenance and assumptions; and
- export both the dataset and an evidence report.

The current PoC architecture remains centered on four stable platform components:

1. **SyntheticDataSpec**
2. **Semantic Validator**
3. **Engine Contract / Registry**
4. **Independent Evaluation Framework**

The generation engine itself should remain replaceable.

### Current first-class generation paths

The initial PoC should continue to support two main paths:

```text
                    USER
                     |
          +----------+----------+
          |                     |
   Define/describe schema   Upload approved data
          |                     |
          v                     v
     Rule generation       Learned generation
     Faker + rules         ARF initially
          |                     |
          +----------+----------+
                     |
                     v
              Synthetic dataset
                     |
                     v
            Independent evaluation
```

Domain-specific behavior, relational synthesis, time series, and differential privacy can then be added as explicit capabilities rather than being implied before they are implemented.

---

## 3. What the PoC should prove

A successful PoC should answer the following questions with evidence.

| Question | Expected PoC evidence |
|---|---|
| Can a nontechnical user describe a dataset? | The assistant translates the request into an editable structured specification. |
| Can a technical user define the same request precisely? | The technical form writes to the same underlying specification. |
| Can data be generated without source records? | Rule/schema mode generates structurally valid data. |
| Can an approved CSV be learned from? | A learned engine produces new records while preserving selected statistical patterns. |
| Are identifiers handled correctly? | Synthetic IDs/UUIDs are regenerated rather than copied. |
| Are assumptions visible? | Every assumption records whether it came from a user, public source, learned estimate, or unresolved proposal. |
| Are unsupported requests rejected clearly? | The engine capability layer prevents unsupported modalities or constraints. |
| Does generation success mean data quality? | No. Evaluation is independent of the synthesizer. |
| Does synthetic automatically mean private? | No. Privacy is separately evaluated and labelled. |
| Can results be reproduced? | Specification, engine/adapter versions, transformations, seeds, warnings, and counts are preserved. |
| Can users understand the output? | UI provides quality, validity, provenance, and limitation reports alongside data export. |

---

## 4. Attendance.csv as the first realistic PoC demonstration

The supplied attendance file contains:

- **28,549 records**
- **12 columns**
- **236 distinct employee/user IDs**
- **735 distinct sign-in dates**
- a date span from **28 April 2023 to 15 May 2025**

Its columns are:

```text
primary_key
attendance_unique_id
entry_or_exit_status
attendance_time_in
attendance_time_out
attendance_is_active
attendance_created_by
attendance_created_date
attendance_user_id
late_status
sign_in_date
extra_hours
```

This is a strong PoC dataset because it contains several semantic types:

- primary keys;
- UUID-like identifiers;
- employee/entity identifiers;
- booleans;
- timestamps;
- calendar dates;
- missing values;
- a constant/near-constant field;
- lateness information; and
- numerical overtime information.

### What the PoC should learn versus regenerate

The platform should distinguish between values to **regenerate** and patterns to **learn**.

For example:

```text
attendance_unique_id
        |
        +--> semantic role: identifier
        +--> do not learn original values
        +--> generate new UUIDs
```

while:

```text
late_status
attendance_time_in
attendance_time_out
extra_hours
        |
        +--> behavioral/statistical attributes
        +--> distributions and relationships may be learned
```

This semantic distinction is one reason the PoC needs a specification and validator rather than relying only on Pandas data types.

---

## 5. The attendance file is suitable for attendance-behavior modeling, not complete employee performance

The existing file can support experiments around:

- attendance frequency;
- punctuality;
- lateness;
- arrival/departure patterns;
- overtime;
- missing clock-outs;
- weekday patterns; and
- changes in attendance behavior over time.

It does **not**, by itself, contain evidence about:

- project completion;
- task quality;
- productivity;
- report quality;
- workload;
- collaboration;
- project deadline adherence;
- rework;
- employee motivation; or
- general job performance.

Therefore the PoC must not claim that such variables were learned from `Attendance.csv`.

New performance-related attributes must come from one of the following:

1. **user-defined synthetic assumptions**;
2. **another approved source dataset**;
3. **approved public/domain statistics or policies**; or
4. an explicitly unresolved proposal awaiting user confirmation.

This provenance distinction should remain visible in the UI and evidence report.

---

## 6. Proposed extensive employee work-behavior attributes

To make the employee example more useful for ML experimentation, the PoC can extend beyond attendance into observable work outcomes.

### Attendance behavior

```text
attendance_rate
punctuality_rate
avg_late_minutes
monthly_overtime_hours
missing_checkout_rate
absence_count
```

### Workload

```text
projects_assigned
tasks_assigned
active_projects
workload_index
average_task_complexity
```

### Project delivery

```text
projects_completed
project_completion_rate
avg_project_completion_days
projects_completed_on_time
deadline_adherence_rate
avg_delay_days
```

### Task behavior

```text
tasks_completed
task_completion_rate
avg_task_completion_hours
overdue_tasks
task_rework_count
```

### Reporting behavior

```text
reports_required
reports_submitted
reports_on_time
report_submission_rate
avg_report_delay_days
report_quality_score
```

### Quality and collaboration

```text
task_quality_score
rework_rate
team_tasks
collaboration_score
avg_response_hours
```

### Development / learning

```text
trainings_assigned
trainings_completed
training_completion_rate
```

### Optional outcome fields

```text
project_delay_risk
task_rework_risk
report_delay_risk
performance_indicator
```

For the PoC, observable outcomes such as `project_delay_risk` or `task_rework_risk` are preferable to an unexplained label such as `good_employee`.

A composite `performance_indicator` should only be included if the formula and its provenance are explicit.

---

## 7. Why these attributes should not simply be appended to Attendance.csv

The current attendance file is approximately at the grain:

```text
ONE ROW = ONE ATTENDANCE EVENT / RECORD
```

However:

```text
ONE PROJECT ROW      = ONE PROJECT
ONE ASSIGNMENT ROW   = ONE EMPLOYEE-PROJECT ASSIGNMENT
ONE TASK ROW         = ONE TASK
ONE REPORT ROW       = ONE REPORT
ONE PERFORMANCE ROW  = ONE EMPLOYEE + ONE EVALUATION PERIOD
```

These entities have different cardinalities.

An employee can have:

```text
1 employee
   |
   +-- many attendance records
   +-- many project assignments
   +-- many tasks
   +-- many reports
   +-- many monthly/quarterly performance periods
```

Forcing all of this into one attendance table would duplicate parent information, create awkward null-heavy columns, distort counts, and make relationships difficult to evaluate.

This is the main reason relational support is worth adding to the PoC.

---

# 8. Proposed employee relational model

A practical relational demonstration could use the following tables.

## 8.1 employees

```text
employee_id              PK
department_id
role
grade
hire_date
employment_status
```

## 8.2 attendance

```text
attendance_id            PK
employee_id              FK -> employees.employee_id
attendance_date
time_in
time_out
late_status
extra_hours
attendance_status
```

## 8.3 projects

```text
project_id               PK
project_type
start_date
planned_end_date
complexity
priority
project_status
```

## 8.4 project_assignments

```text
assignment_id            PK
project_id               FK -> projects.project_id
employee_id              FK -> employees.employee_id
assigned_date
assignment_deadline
completion_date
contribution_percentage
assignment_status
```

This junction table is important because projects and employees can naturally form a many-to-many relationship.

## 8.5 tasks

```text
task_id                   PK
project_id                FK -> projects.project_id
employee_id               FK -> employees.employee_id
assigned_date
deadline
completed_date
complexity
task_status
rework_count
quality_score
```

## 8.6 reports

```text
report_id                 PK
project_id                FK -> projects.project_id
employee_id               FK -> employees.employee_id
required_date
due_date
submitted_date
report_status
quality_score
```

## 8.7 employee_performance_periods

```text
performance_period_id     PK
employee_id               FK -> employees.employee_id
period_start
period_end

attendance_rate
punctuality_rate
overtime_hours

project_completion_rate
deadline_adherence_rate

task_completion_rate
rework_rate

report_submission_rate
average_quality_score

workload_index
performance_indicator
```

The last table is mainly an **analytical summary table**. Most of its values can be calculated from event-level tables instead of generated independently.

That distinction is important because duplicated independently generated metrics can contradict underlying records.

---

# 9. Recommended relational dependency graph

```text
                         employees
                             |
          +------------------+-------------------+
          |                  |                   |
          v                  v                   v
     attendance       project_assignments      reports
                             |                   ^
                             |                   |
                             v                   |
                          projects -------------+
                             |
                             v
                            tasks

employees
   |
   +----------------------> employee_performance_periods
                                ^
                                |
                  derived/evaluated from event tables
```

A stronger version is:

```text
employees --------------------------+
   |                                |
   v                                |
attendance                          |
                                    |
projects                            |
   |                                |
   v                                |
project_assignments <---------------+
   |
   +------> tasks
   |
   +------> reports

all event tables
       |
       v
employee_performance_periods
```

---

# 10. A useful intermediate step before full relational synthesis

The current PoC is deliberately single-table.

Therefore relational functionality does not have to be introduced all at once.

A useful bridge is an aggregated table:

## `employee_monthly_behavior.csv`

```text
employee_id
year_month

attendance_rate
punctuality_rate
avg_late_minutes
overtime_hours

projects_assigned
projects_completed
project_completion_rate
deadline_adherence_rate

tasks_assigned
tasks_completed
task_completion_rate
overdue_tasks
rework_count

reports_required
reports_submitted
reports_on_time
report_submission_rate

average_quality_score
workload_index
```

Each row means:

```text
ONE EMPLOYEE + ONE MONTH
```

This allows the current single-table PoC to demonstrate extensive employee behavior while the relational engine is being designed.

It should be described as a **PoC bridge**, not the final data architecture.

---

# 11. What relational functionality changes in the platform

Relational support is not simply "allow multiple CSV uploads."

It introduces several new requirements.

## 11.1 SyntheticDataSpec must become multi-table aware

The current specification should evolve conceptually from:

```json
{
  "columns": {},
  "constraints": []
}
```

toward:

```json
{
  "tables": {
    "employees": {},
    "attendance": {},
    "projects": {},
    "project_assignments": {},
    "tasks": {},
    "reports": {}
  },

  "relationships": [
    {
      "parent_table": "employees",
      "parent_key": "employee_id",
      "child_table": "attendance",
      "child_key": "employee_id",
      "cardinality": "one_to_many"
    }
  ]
}
```

The specification should support:

- tables;
- primary keys;
- foreign keys;
- relationship type;
- optionality;
- child-count/cardinality behavior;
- cross-table constraints;
- generation order;
- provenance;
- privacy unit/protected entity; and
- evaluation requirements.

## 11.2 The semantic validator becomes more important

The validator should check:

- primary-key uniqueness;
- foreign-key validity;
- unknown parent references;
- cycles where unsupported;
- contradictory cardinalities;
- cross-table data types;
- cross-table date rules;
- generation ordering;
- unsupported many-to-many relationships;
- incompatible engine capabilities; and
- whether the protected entity is correctly defined for privacy-sensitive generation.

Examples:

```text
task.employee_id must exist in employees.employee_id

project_assignment.project_id must exist in projects.project_id

completion_date >= assigned_date

submitted_date >= required_date

completed tasks must have completed_date
```

---

# 12. Relational engine contract

The current adapter contract can remain conceptually stable, but capabilities and input/output structures must expand.

```python
class EngineAdapter:
    def capabilities(self): ...
    def validate_request(self, spec): ...
    def prepare(self, spec, source=None): ...
    def fit(self, prepared_input): ...
    def sample(self, artifact, count=None, conditions=None): ...
    def diagnostics(self): ...
```

For relational mode, `source` and generated output become mappings:

```python
source = {
    "employees": employees_df,
    "attendance": attendance_df,
    "projects": projects_df,
    "assignments": assignments_df
}
```

and:

```python
synthetic = {
    "employees": synthetic_employees,
    "attendance": synthetic_attendance,
    "projects": synthetic_projects,
    "assignments": synthetic_assignments
}
```

The engine capability declaration should explicitly state:

```text
single_table: true/false
multi_table: true/false
one_to_many: true/false
many_to_many: true/false
conditional_sampling: true/false
cross_table_constraints: true/false
privacy_mechanism: ...
```

The LLM must not be allowed to select relational mode unless the chosen adapter declares the required capability.

---

# 13. Generation strategies for relational PoC support

Relational support can be introduced using several levels of sophistication.

## Strategy A — rule-based parent-first generation

This is the easiest relational PoC extension.

Example:

```text
Generate employees
       |
       v
For each employee sample attendance-count distribution
       |
       v
Generate attendance and attach valid employee_id
       |
       v
Generate projects
       |
       v
Generate assignments
       |
       v
Generate tasks/reports using valid parent keys
```

This proves:

- schema graph handling;
- foreign-key generation;
- cardinality controls;
- relational constraints; and
- UI/schema editing.

It does not yet prove learned cross-table synthesis.

## Strategy B — hybrid learned + relational rules

Use learned single-table engines for attributes, but let the platform control relationships.

Example:

```text
ARF learns employee attributes

ARF learns attendance attributes

Platform learns/defines:
- attendance rows per employee
- project assignments per employee
- tasks per project
- reports per project

Relationship controller creates IDs/FKs
```

This is a useful intermediate PoC because the existing ARF adapter can still be reused.

However, it may fail to preserve complex cross-table dependencies.

## Strategy C — native relational synthesizer

A relational model learns both table content and relationships.

This is the longer-term target.

Candidate research/reference systems include:

- SDV multi-table concepts and metadata/evaluation;
- REaLTabFormer-style parent/child relational synthesis;
- newer research into graph-based and other relational generative models.

No relational generator should be adopted only because it has a multi-table API. It should be benchmarked against the PoC's own acceptance criteria.

---

# 14. Why flattening the database should not be the default solution

A tempting shortcut is:

```text
employees
JOIN attendance
JOIN projects
JOIN tasks
JOIN reports
        |
        v
one huge table
        |
        v
single-table synthesizer
```

This is useful for some ML feature tables but is a poor default synthetic-database strategy.

It can:

- duplicate employee attributes many times;
- distort employee and project frequency distributions;
- lose original cardinality;
- create sparse/null-heavy data;
- create inconsistent regenerated relationships; and
- make reconstructing normalized tables difficult.

Relational generation should therefore preserve the database graph where possible.

Flattened analytical tables remain useful as **derived ML datasets**, not as the source-of-truth relational representation.

---

# 15. Relational evaluation requirements

Single-table evaluation is no longer enough.

A multi-table synthetic dataset should be evaluated at several levels.

## 15.1 Structural validity

Check:

- required tables exist;
- required columns exist;
- correct types;
- primary-key uniqueness;
- valid foreign keys;
- no unexpected orphan rows.

## 15.2 Cardinality fidelity

Compare distributions such as:

```text
attendance records per employee
projects per employee
employees per project
tasks per project
reports per project
```

For example:

```text
REAL:
employees with 1-2 projects      40%
employees with 3-5 projects      45%
employees with >5 projects       15%

SYNTHETIC:
compare the same distribution
```

## 15.3 Cross-table relationship fidelity

Test whether meaningful relationships survive.

Examples:

```text
project complexity
      |
      +--> completion duration

employee workload
      |
      +--> overdue task frequency

project assignment count
      |
      +--> report volume
```

## 15.4 Temporal validity

Examples:

```text
project.start_date <= assignment.assigned_date

assignment.assigned_date <= completion_date

report.required_date <= submitted_date

performance period contains the relevant events
```

## 15.5 Task-specific utility

Example:

```text
Train delay-risk model using synthetic relational/derived data
               |
               v
Evaluate using an independently authorized real test set
```

Utility should remain purpose-specific rather than collapsed into one universal score.

## 15.6 Privacy evaluation

Relational data introduces additional privacy questions because the protected unit may be an **employee**, not an individual row.

An employee may appear across:

```text
attendance
assignments
tasks
reports
performance periods
```

Privacy auditing therefore needs to reason about the full entity footprint, repeated records, and repeated generation/query operations.

No "safe to share" claim should be inferred from referential validity or statistical quality.

---

# 16. Evidence from existing relational synthetic-data work

Relational synthesis is materially harder than single-table generation because a system must preserve table-level distributions **and** relationships/cardinalities between tables.

Recent benchmarking research reports that relational synthesis remains challenging and that evaluated methods are not able to produce relational datasets that are indistinguishable from real data across the board. This supports treating relational synthesis as a separate PoC capability with its own benchmarks rather than assuming a single-table generator will automatically generalize.

Relevant research:
- Hudovernik, Jurkovič & Štrumbelj, *Benchmarking the Fidelity and Utility of Synthetic Relational Data* (2024): https://arxiv.org/abs/2410.03411

SDMetrics provides useful reference concepts for multi-table evaluation, including:
- multi-table metadata with primary/foreign-key relationships;
- relationship validity / referential integrity;
- multi-table quality reports; and
- cardinality-shape similarity.

References:
- https://docs.sdv.dev/sdmetrics/getting-started/metadata/multi-table-metadata
- https://docs.sdv.dev/sdmetrics/reports/quality-report/multi-table-api
- https://docs.sdv.dev/sdmetrics/data-metrics/diagnostic/referentialintegrity
- https://docs.sdv.dev/sdmetrics/data-metrics/quality/cardinalityshapesimilarity

These concepts can be reused in our own evaluator even if SDV itself is not selected as the platform generation dependency.

REaLTabFormer is also relevant as a research/reference implementation for relational tabular synthesis and is worth benchmarking in a later relational-engine experiment:
- https://github.com/avsolatorio/REaLTabFormer
- https://github.com/avsolatorio/REaLTabFormer-Experiments

The existing project review should still perform a separate license/deployment review before incorporating third-party code into the platform.

---

# 17. UI implications of relational functionality

The UI becomes a first-class part of the relational PoC.

## 17.1 Dataset ingestion

The user should be able to:

```text
[ Upload one table ]
[ Upload multiple related tables ]
[ Describe a new relational dataset ]
```

For multiple uploads, the profiler should attempt to identify:

- likely primary keys;
- likely foreign keys;
- matching column names/types;
- parent/child tables;
- cardinality;
- missing references; and
- temporal relationships.

All inferred relationships remain proposals until confirmed.

## 17.2 Schema graph

The UI should visually display:

```text
Employees
   |
   +------< Attendance
   |
   +------< Project Assignments >------ Projects
   |
   +------< Reports
```

The user should be able to edit:

- relationship endpoints;
- key columns;
- cardinality;
- optionality; and
- generation rules.

## 17.3 LLM assistant

A user could say:

> I want 500 synthetic employees, around two years of attendance, 2-6 projects per employee per year, tasks under projects, and monthly performance summaries.

The assistant should translate this into the relational specification and identify assumptions such as:

```text
? department distribution
? project complexity distribution
? task count per project
? probability of late completion
? reporting frequency
? relationship between workload and delay
```

The assistant proposes; the user approves.

## 17.4 Generation report

A relational generation report should include:

```text
Requested:
500 employees

Generated:
500 employees
112,840 attendance records
1,936 project assignments
438 projects
14,509 tasks
3,772 reports
12,000 performance-period rows

Referential integrity:
100%

Rejected rows:
...

Repairs:
...

Relationship/cardinality warnings:
...
```

---

# 18. Proposed phased implementation plan

## Phase 1 — Current single-table PoC

Keep:

- Faker/rule generation;
- ARF learned generation;
- CSV upload and profiling;
- SyntheticDataSpec;
- semantic validation;
- evidence reports;
- LLM specification assistant.

Employee demonstration:

```text
Attendance.csv
      |
      v
employee_monthly_behavior.csv
```

New project/task/report attributes are clearly labelled as synthetic assumptions unless supported by additional approved datasets.

## Phase 1.5 — Relational specification + rule engine

Add:

- multiple tables in SyntheticDataSpec;
- primary/foreign keys;
- relationship graph;
- cardinality rules;
- cross-table semantic validator;
- parent-first rule-based generation;
- relational UI/schema graph;
- relational validity metrics.

This phase proves the **platform architecture for relational data** without requiring a sophisticated relational ML synthesizer.

## Phase 2 — Hybrid relational learning

Add:

- per-table learned models;
- learned child-count/cardinality distributions;
- platform-managed foreign keys;
- relationship-conditioned generation where feasible;
- relational fidelity evaluation.

Benchmark against rule-only relational generation.

## Phase 3 — Native relational synthesis experiment

Evaluate at least one dedicated relational synthesizer.

Compare:

- structural validity;
- cardinality fidelity;
- cross-table statistical fidelity;
- downstream ML utility;
- runtime/resource cost;
- privacy risk;
- integration complexity;
- license/deployment suitability.

Do not replace the platform specification with the selected engine's proprietary/internal metadata format.

## Phase 4 — Sensitive relational-data mode

Only after sufficient evidence:

- institution-local profiling/training;
- explicit protected-entity definition;
- privacy threat model;
- attack/audit harness;
- repeated-fit/repeated-query considerations;
- release policy separated from automatic quality scores.

---

# 19. Recommended relational PoC acceptance gates

| Gate | Evidence |
|---|---|
| Schema graph | Multiple tables and relationships represented in one versioned specification |
| Referential integrity | No unreported orphan child records |
| Key correctness | Synthetic primary keys unique; foreign keys valid |
| Cardinality | Parent-child count distributions evaluated |
| Cross-table validity | Declared relational constraints pass |
| Temporal consistency | Cross-table date/event ordering constraints pass |
| Provenance | Learned versus user-defined relationship assumptions are distinguishable |
| Capability control | Single-table engines cannot silently accept relational requests |
| Generation completeness | Generated row/table counts reported explicitly |
| Evaluation independence | Relational quality evaluated outside the generator |
| UI usability | User can inspect/edit the relationship graph without editing code |
| LLM correctness | Relationship/key/cardinality extraction tested against labelled examples |
| Privacy labelling | Relational validity is never presented as proof of safe release |
| Reproducibility | Specification, transforms, seeds, versions, and input hashes preserved |

---

# 20. Employee behavioral modeling use cases enabled by the relational extension

A relational employee dataset can support safer and more meaningful ML experimentation than a generic "employee performance score."

Useful experimental targets include:

### Project delivery

```text
project_delay_risk
expected_completion_duration
deadline_miss_probability
```

### Task outcomes

```text
task_rework_risk
overdue_task_risk
expected_task_completion_time
```

### Reporting

```text
report_delay_risk
missing_report_risk
```

### Workload and process analysis

```text
workload imbalance
high-overtime periods
attendance/project workload interactions
project staffing patterns
```

### System development

The same data can also support:

- HR/project-management dashboard development;
- database and ETL testing;
- API performance/load testing;
- feature-engineering experiments;
- data-science training;
- model-pipeline testing; and
- controlled demonstrations where production data cannot be distributed.

Synthetic data should remain a development and experimentation aid. Any model intended to affect real employment decisions such as promotion, discipline, hiring, termination, or compensation requires separate validation, governance, and fairness assessment using appropriately authorized evidence.

---

# 21. Main architectural conclusion

The relational extension should **not change the core philosophy of the PoC**.

The core should remain:

```text
               User / UI / LLM
                      |
                      v
             SyntheticDataSpec
                      |
                      v
              Semantic Validator
                      |
                      v
                Engine Registry
                      |
          +-----------+-----------+
          |                       |
   Single-table engines     Relational engines
          |                       |
          +-----------+-----------+
                      |
                      v
              Generated dataset
                      |
                      v
          Independent evaluation
                      |
                      v
           Dataset + evidence report
```

The platform should own:

- specification;
- validation;
- capability checks;
- provenance;
- orchestration;
- evaluation; and
- reporting.

Generation engines should remain replaceable workers.

This allows the PoC to start small with `Attendance.csv` and a single-table employee monthly behavioral dataset while providing a clean path toward realistic multi-table datasets covering employees, attendance, projects, assignments, tasks, reports, and performance periods.

---

# 22. Recommended immediate next step

Do **not** immediately replace the current single-table PoC.

The recommended next implementation sequence is:

```text
1. Finish current single-table specification and validator
2. Demonstrate Attendance.csv -> synthetic attendance
3. Add employee_monthly_behavior PoC scenario
4. Draft SyntheticDataSpec relational extension
5. Implement relationship validator
6. Implement rule-based multi-table employee generator
7. Add schema-graph UI
8. Add relational evaluation
9. Benchmark a native relational synthesizer
10. Decide whether learned relational generation belongs in the production architecture
```

This sequence gives the project demonstrable results at each stage and keeps the research claims aligned with what has actually been implemented and evaluated.
