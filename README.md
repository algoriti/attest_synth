# Attest Synth

**Synthetic data that comes with its evidence.**

Attest Synth generates synthetic structured data from a versioned specification, and returns
an evidence report stating what was actually done and what the result does *not*
support.

The second half is the point. Anyone can produce plausible-looking rows. The hard part
is knowing whether you should trust them.

```bash
cd platform/backend && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
cd ../backend && python -m uvicorn synthetic_platform.api:app --port 8770
# open http://localhost:8770
```

---

## Why it exists

Real operational data contains business rules that look like ordinary columns.

Profiling a real attendance export, a quarter of its columns turned out to be formulas
rather than behaviour — an "is late" flag that was really just *clocked in after a
fixed cutoff*, an overtime figure that was really just *hours past a standard day*.

Hand that to a machine-learning generator and it imitates all three as statistics. The
distributions look healthy and the rows are nonsense: six-hour shifts carrying nine
hours of overtime, staff marked late at ten past six in the morning.

Same generator, same data, with and without Attest Synth:

| Check | Generator alone | Through Attest Synth |
|---|---:|---:|
| Overtime contradicts shift length | 592 | **0** |
| Late flag contradicts clock-in | 48 | **0** |
| Worst-case contradiction rate | **39.47%** | **0.00%** |

The fix is not a better generator. It is not asking the generator to produce those
columns at all — they are computed afterwards from a declared formula, so they cannot
disagree with the columns they depend on.

---

## What it does

- **Profiles** an uploaded CSV and proposes a specification — column roles, business
  rules it found, and data-quality problems it will not fix silently.
- **Validates** before generating. An impossible request fails in milliseconds with an
  explanation instead of running for minutes and producing plausible nonsense.
- **Generates** through replaceable engines: declared rules, an adversarial random
  forest, linked relational tables, and a deliberately bad baseline to measure against.
- **Reports** completeness, every repair by column, which values were computed rather
  than generated, and every assumption nobody has confirmed.

It works on any single-table CSV, and on linked tables. Attendance was the dataset that
exposed the design; it is not the scope. Measured across banking, chemistry and
education data with no domain-specific code, synthetic data beat the do-nothing
baseline in all three and trailed real data in all three — good enough to build and
test against, not good enough to draw conclusions from.

---

## What it will not do

Attest Synth refuses to overclaim. Asking a specification to permit a release claim is a
validation **error**, not a setting.

There is **no privacy mechanism** here, and the evidence for why that matters is in the
repository: a control that copied real rows verbatim scored 0.291 against real data's
0.306. High utility and zero privacy are demonstrably compatible. A good score is not a
safety argument.

Not built, deliberately: differential privacy, learned relational synthesis, an LLM
assistant, and modalities beyond structured tables. Each has its own acceptance
criteria before it ships.

---

## Documentation

| | |
|---|---|
| [Platform README](platform/README.md) | Engines, roles, the expression vocabulary, running it |
| [Literature review](literature-review/README.md) | The research and benchmark the design is built on |

---

## Status

Proof of concept. 108 tests. Job and upload state is in memory; moving it to PostgreSQL
touches one file.

Everything claimed here is measured from the code in this repository. Where a claim
turned out to be wrong, the correction is written down rather than quietly removed —
the same standard the generated data is held to.
