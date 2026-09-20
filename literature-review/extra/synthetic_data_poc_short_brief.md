# Synthetic Data Platform PoC — Short Project Brief

## 1. What is this PoC?

This project is a **general-purpose synthetic data platform PoC**.

Its purpose is to help technical and nontechnical users create useful structured synthetic datasets for:

- AI/ML development
- application and API testing
- analytics/dashboard development
- database and ETL testing
- training and education
- scenarios where real data is unavailable or restricted

The platform is **not just a fake CSV generator**. It separates:

```text
User requirement
      ↓
Synthetic data specification
      ↓
Validation
      ↓
Generation engine
      ↓
Synthetic data
      ↓
Evaluation
      ↓
Dataset + evidence report
```

This design allows us to change or add generation engines without rebuilding the whole platform.

---

## 2. What has been done so far?

The project started with a literature and software review of synthetic-data approaches including:

- Faker
- Adversarial Random Forests / `arfpy`
- DataSynthesizer
- Copulas
- CTGAN / TVAE
- Synthcity
- SmartNoise
- SDV
- REaLTabFormer
- Synthea
- SDMetrics
- TAPAS

We also ran comparative experiments before choosing the first PoC engines.

The platform has now moved beyond research into a **working PoC**.

Current implementation includes:

- web UI
- CSV upload
- dataset profiling
- editable data specification
- rule/Faker generation
- ARF learned generation
- independent-sampling baseline
- early relational rule generation
- constraints and validation
- evaluation reports
- CSV/specification/evidence downloads

The latest implementation review recorded **60 passing backend tests** and a successful frontend build.

---

# 3. Current PoC engines

## A. Faker + Rules Engine

### What it is for

Faker is used when we **do not need to learn from an existing dataset**.

Example:

> Generate 20,000 employees with IDs, departments, grades, dates and salary ranges.

### How it works

The user or system provides explicit rules:

```text
employee_id → generate new ID
department  → choose from approved categories
age         → 18–60
hire_date   → valid date range
email       → Faker email provider
```

Then:

```text
Specification
     ↓
Faker + rules
     ↓
Synthetic rows
     ↓
Constraint checks
```

### Strength

It is simple, fast and transparent.

### Limitation

Faker does **not learn real population relationships**.

If we tell it:

```text
age = 18–60
salary = 500,000–5,000,000
```

it does not automatically know how age, role and salary should relate unless we define that relationship ourselves.

---

## B. ARF / `arfpy` Engine

### What it is for

ARF is used when we have an **approved source table** and want to learn its patterns.

Example:

> Learn from an attendance dataset and generate new synthetic attendance records.

### How ARF works

ARF means **Adversarial Random Forest**.

It first creates deliberately weak synthetic data, then trains a Random Forest to distinguish:

```text
REAL DATA
vs
SYNTHETIC DATA
```

The forest learns what makes the real data different.

The process repeats so that the generated data becomes harder to distinguish from the real data.

Then ARF estimates distributions inside the learned forest regions and samples new records.

Simplified:

```text
Real dataset
     ↓
Create initial fake rows
     ↓
Random Forest learns real vs fake differences
     ↓
Improve learned structure
     ↓
Estimate local distributions
     ↓
Generate new synthetic rows
```

In `arfpy`, the main stages are approximately:

```text
ARF
 ↓
FORDE
 ↓
FORGE
```

- **ARF** learns the structure.
- **FORDE** estimates distributions.
- **FORGE** generates the new synthetic records.

### Strength

ARF can preserve relationships between mixed tabular variables better than simple independent sampling.

### Limitation

ARF is currently a **single-table learned generator**.

It also does **not provide a formal privacy guarantee**.

---

## C. Independent Sampling Baseline

This engine samples each column separately.

Example:

```text
age        → sample age distribution
department → sample department distribution
salary     → sample salary distribution
```

It is intentionally simple.

Its role is mainly to answer:

> Does ARF actually preserve useful dependencies better than a simple baseline?

It is therefore an **experimental comparison engine**, not our main quality target.

---

## D. Relational Rules Engine

The PoC also has an early rule-based relational capability.

It can generate parent records first and then assign valid parent IDs to child records.

Example:

```text
employees
   |
   +---- attendance
   |
   +---- project_assignments ---- projects
```

This allows us to start testing:

- primary keys
- foreign keys
- parent/child generation
- one-to-many relationships
- junction tables

However, the relational engine is **still being strengthened**. General relational correctness is not yet claimed.

---

# 4. Why did we not start with CTGAN, Synthcity, SDV or SmartNoise?

We did **not reject these tools**.

We deliberately postponed them.

## CTGAN / neural models

CTGAN and other neural approaches are useful, but they add:

- heavier dependencies
- longer training
- more tuning
- more reproducibility concerns

Also, using a neural model does not automatically guarantee better utility or privacy.

We plan to benchmark neural engines later under the same evaluation rules.

---

## Synthcity

Synthcity provides many generators through a plugin framework.

It is useful as a future **isolated engine worker**, but it has a much larger dependency environment than our current PoC.

We do not want our whole platform architecture to depend on Synthcity.

Instead:

```text
Our Platform
     ↓
Engine Adapter
     ↓
Synthcity worker later
```

---

## SDV / standalone CTGAN / Copulas

These tools are technically useful, but the versions reviewed have **Business Source License (BSL)** considerations.

Because this project may eventually become a reusable institutional platform, licensing must be reviewed carefully before making them core dependencies.

We still use their ideas and can benchmark them as comparators.

---

## SmartNoise

SmartNoise is important because it supports **differentially private synthetic-data mechanisms**.

However, privacy is not something we want to enable simply by adding an `epsilon` textbox.

A valid DP workflow requires correct handling of:

- protected entity
- data bounds/domains
- preprocessing
- privacy budget
- repeated training
- released statistics

Therefore SmartNoise is planned as a **separate privacy experiment** after the core PoC is stable.

---

# 5. Where does the LLM fit?

The LLM is planned as an **assistant**, not the main synthetic-data generator.

Its role will be:

```text
User:
"I need employee project-performance data"
        ↓
LLM
        ↓
Proposed SyntheticDataSpec
        ↓
User review
        ↓
Validator
        ↓
Supported engine
```

The LLM can help:

- understand natural-language requirements
- identify missing information
- propose fields
- propose constraints
- explain reports

But the LLM cannot silently invent facts and present them as learned evidence.

Every proposal must still pass the platform validator.

---

# 6. What the PoC can demonstrate today

Today the PoC can demonstrate:

### Without source data

```text
Schema / rules
      ↓
Faker
      ↓
Synthetic dataset
```

### With an approved single table

```text
CSV
 ↓
Profile
 ↓
Review specification
 ↓
ARF
 ↓
Synthetic dataset
 ↓
Evaluation
```

### With simple relational scenarios

```text
Parent tables
      ↓
Relational rules
      ↓
Child tables with valid parent references
```

The output is not only the generated data.

The platform also aims to return:

```text
Synthetic dataset
+
Specification
+
Assumptions
+
Warnings
+
Validation results
+
Evaluation evidence
```

---

# 7. What we are working on next

The immediate priority is **not adding more engines**.

We first need to strengthen the evidence produced by the current PoC.

Current roadmap:

```text
1. Strengthen final validation and evaluation
               ↓
2. Complete relational rules
               ↓
3. Improve nontechnical UI/schema authoring
               ↓
4. Validate the employee attendance use case
               ↓
5. Benchmark the actual platform across domains
               ↓
6. Add and evaluate the LLM assistant
               ↓
7. Test neural, DP and native relational engines
```

---

# 8. Main project idea

The project should be understood as:

> **An extensible synthetic-data platform where users define what data they need, the platform validates that request, a suitable engine generates the data, and an independent evaluation layer explains what was generated and how well it meets the intended purpose.**

The most important principle is:

```text
Synthetic data
≠ automatically private

Valid data
≠ automatically realistic

Realistic data
≠ automatically useful

Useful for one task
≠ useful for every task
```

That is why the PoC includes **generation + validation + evaluation + provenance**, rather than only a synthetic-data model.
