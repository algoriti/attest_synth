# Synthetic Data Platform — proof of concept

A specification-driven platform for generating synthetic structured data, with an
evidence report that states what was actually done and what the result does not
support.

The platform owns the specification, validation, capability checks, provenance,
orchestration, evaluation and reporting. Generation engines are replaceable workers.
An engine never grades its own output.

---

## The problem this exists to solve

Real operational data contains business rules that look like ordinary columns.

Profiling the 28,549-row attendance export that motivated this build, three of its
twelve columns turned out to be deterministic formulas rather than behaviour:

| Column | Rule | Agreement |
|---|---|---:|
| `entry_or_exit_status` | equals "`attendance_time_out` is missing" | 100.00% |
| `extra_hours` | equals `round(shift_hours − 6)` | 99.15% |
| `late_status` | equals "clocked in after 07:45 local" | 97.75% |

Hand that table to a learned generator and it models all three as statistical columns.
Every marginal distribution looks healthy, and the rows are nonsense: six-hour shifts
carrying nine hours of overtime, staff marked late who clocked in at six in the
morning.

Running the same generator over the same data, with and without the platform:

| Check | Naive (all columns learned) | Through the platform |
|---|---:|---:|
| `extra_hours` contradicts shift length | 791 | **0** |
| `late_status` contradicts clock-in | 84 | **0** |
| Worst-case contradiction rate | 39.55% | **0.00%** |

The generator is the same. The difference is that derived columns are *computed after
generation* from a declared formula, so they cannot disagree with the columns they
depend on.

---

## Quick start

```bash
# backend
cd platform/backend
pip install -r requirements.txt
python -m uvicorn synthetic_platform.api:app --port 8770

# frontend (development, with hot reload)
cd platform/frontend
npm install
npm run dev
```

For a single-process deployment, build the frontend once and let the API serve it:

```bash
cd platform/frontend && npm run build
cd ../backend && python -m uvicorn synthetic_platform.api:app --port 8770
# open http://localhost:8770
```

Run the tests and the demonstration:

```bash
cd platform/backend
python -m pytest tests/ -q              # 43 tests
python demo_attendance.py --rows 2000   # naive vs platform comparison
```

---

## How it works

```
   UI / LLM / API
        |
        v
  SyntheticDataSpec  ......  the contract; nothing else owns it
        |
        v
  Semantic validator  .....  rejects impossible requests before any work starts
        |
        v
  Engine registry  ........  capability check; a single-table engine cannot
        |                    silently accept a relational request
        v
  Engine  .................  generates ONLY the columns marked "learned" or "rule"
        |
        v
  Derivation  .............  computes "derived" columns from declared formulas
        |
        v
  Normalisation  ..........  enforces types and bounds, counting every repair
        |
        v
  Evaluation  .............  constraints / fidelity / utility, run by the platform
        |
        v
  Dataset + evidence report
```

### Semantic roles

The role decides what a generator is even allowed to see.

| Role | Meaning |
|---|---|
| `identifier` | Regenerated. A source UUID is never copied into synthetic output. |
| `learned` | A generator may model this column. |
| `rule` | Sampled from an explicit declared rule. |
| `derived` | Computed from other columns *after* generation. |
| `constant` | One value throughout. |
| `empty` | No observed values; emitted as null. |

### Derived-column expressions

Formulas are a small typed tree, not Python or SQL — specifications arrive over HTTP
and from an LLM, so there is no `eval()` here and no way to reach one. Unknown
operators are rejected by the validator.

```json
{
  "name": "extra_hours",
  "role": "derived",
  "formula": {
    "op": "clip",
    "args": [
      { "op": "round", "args": [
        { "op": "sub", "args": [{ "col": "shift_hours" }, { "const": 6 }] }
      ]},
      { "const": 0 },
      { "const": 14 }
    ]
  }
}
```

Available operators cover arithmetic, comparison, logic, null handling and time
(`duration_hours`, `time_of_day`, `day_of_week`, `add_days`, …).

### Engines

| Engine | Source records | Multi-table | Notes |
|---|---|---|---|
| `rules` | not needed | no | Faker plus declared rules |
| `relational_rules` | not needed | **yes** | Parent-first; referential integrity by construction |
| `arf` | required | no | Adversarial random forest, MIT, CPU only |
| `independent` | required | no | Baseline: matches marginals, destroys relationships |

An engine declares what it can do, and the validator enforces it before any work
starts. ARF, for instance, declares no support for `timestamp` or `date`, and a
ceiling of 1,000 category levels. Both limits are real: arfpy raises a `TypeError` on
a datetime, and models an object column as a factor at roughly quadratic cost, so
21,790 distinct timestamps ran for minutes instead of failing. Unsupported requests
are now rejected in milliseconds with a message saying what to do instead — and, for
temporal columns, with a proposed rewrite.

### When an engine cannot model a column

The rejection comes with a suggested fix. A timestamp is split into hour-of-day and
day-of-week, learned as ordinary numbers, then rebuilt afterwards as a derived column.
A date gets weekday only, because a date sits at midnight and an extracted hour would
be constant — which does not merely teach the model nothing, it makes arfpy fail
fitting a truncated normal with zero scale.

The mechanism is a lookup over two declared facts, with no model involved. The
*content* is still a default nobody asked for, so every column it adds is recorded as
`assistant_proposed` and appears in the report's open assumptions until someone
accepts it. Nothing is applied unless explicitly named.

Two honest limits on the rewrite: rebuilt values fall inside a single reference week,
so they keep working patterns but not the original calendar date; and two rebuilt
timestamps are independent, so a `less_or_equal` constraint is what keeps a clock-out
after its clock-in.

### Known upstream fragility

arfpy 0.1.1 fails when the forest splits until a leaf holds one distinct value for a
numeric column, raising a bare SciPy "Domain error in arguments". It becomes more
likely with scale — on the attendance features it succeeded at 8,000 rows and failed
at 16,000. The adapter escalates its minimum leaf size (5 → 20 → 50) rather than
giving up, which also happens to be faster (79s against 106s at 16,000 rows), and
records the retry in the report's warnings. If every rung fails, the error names the
likely columns and the ways out.

`independent` is kept deliberately. It is the floor every utility number is measured
against — on the education benchmark it scored 3.967 MAE against real data's 0.994
while matching the marginals almost perfectly.

### Relational generation

Parents are generated first and each child row is handed a key from a parent that
already exists, so an orphan row is not representable rather than merely unlikely. The
four-table employee example produces 100% referential integrity across three
relationships, including a junction table with two parents.

---

## What the platform will not do

- **It will not claim privacy.** No engine here applies a formal privacy mechanism.
  Setting `release_claim_permitted: true` is a validation *error*, and
  `mechanism: "differential_privacy"` is rejected because no DP engine is registered.
  In the benchmark behind this platform, a control that copied real training rows
  verbatim reached 0.291 average precision against real data's 0.306 — high utility
  and zero privacy are demonstrably compatible.
- **It will not hide incomplete results.** A request for 10,000 rows answered with
  8,000 is reported as incomplete.
- **It will not hide repairs.** Type and bound corrections are counted per column and
  shown before the download link.
- **It will not silently invent.** Every unconfirmed assumption is listed in the
  report with its origin.
- **It will not let one metric stand in for another.** Fidelity, constraints and
  utility are reported separately, because good marginals routinely coexist with
  useless data.

---

## Layout

```
platform/
├── backend/
│   ├── synthetic_platform/
│   │   ├── spec.py         SyntheticDataSpec, roles, provenance, expressions
│   │   ├── validator.py    semantic validation; returns all findings at once
│   │   ├── derive.py       expression evaluator and dependency ordering
│   │   ├── profile.py      CSV profiler; proposes roles, finds business rules
│   │   ├── evaluate.py     constraints, fidelity, predictive utility
│   │   ├── pipeline.py     orchestration and the evidence report
│   │   ├── api.py          FastAPI; generation runs as a background job
│   │   └── engines/        base contract + rules / learned / relational
│   ├── specs/              three ready-made example specifications
│   ├── tests/              43 tests
│   └── demo_attendance.py  naive vs platform comparison on real data
└── frontend/               React + TypeScript + Recharts
```

---

## Status

Proof of concept. Job and upload state is in memory; moving it to PostgreSQL touches
nothing outside `api.py`. Not yet built: the LLM specification assistant, learned
relational synthesis, differential privacy, and privacy auditing. Those are deliberate
gaps with their own acceptance criteria, not oversights.
