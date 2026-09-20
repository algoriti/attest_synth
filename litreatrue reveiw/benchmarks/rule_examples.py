"""Executable schema-only examples; every distribution is an invented scenario."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from faker import Faker

OUT = Path(__file__).resolve().parent / "results" / "rule_examples"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(2026)
fake = Faker("en_US")
fake.seed_instance(2026)
results = []

start = time.perf_counter()
rows = []
for i in range(1000):
    quantity = int(rng.integers(1, 11))
    cents = int(rng.integers(100, 20001))
    ordered = datetime(2026, 1, 1) + timedelta(days=int(rng.integers(0, 200)))
    shipped = ordered + timedelta(days=int(rng.integers(0, 8)))
    rows.append({"order_id": f"ORD-{i:06d}", "display_name": fake.name(), "quantity": quantity,
                 "unit_price_cents": cents, "total_cents": quantity*cents,
                 "ordered_at": ordered.isoformat(), "shipped_at": shipped.isoformat()})
df = pd.DataFrame(rows)
checks = {"unique_order_id": bool(df.order_id.is_unique), "correct_total": bool((df.total_cents == df.quantity*df.unit_price_cents).all()),
          "shipment_not_before_order": bool((df.shipped_at >= df.ordered_at).all())}
df.to_csv(OUT / "retail.csv", index=False)
results.append({"case": "retail", "rows": len(df), "seconds": time.perf_counter()-start, "checks": checks})

start = time.perf_counter()
df = pd.DataFrame({"student_id": [f"STU-{i:06d}" for i in range(1000)], "credits_attempted": rng.integers(1, 31, 1000)})
df["credits_passed"] = [rng.integers(0, n+1) for n in df.credits_attempted]
df["completion_fraction"] = df.credits_passed / df.credits_attempted
df.to_csv(OUT / "education.csv", index=False)
results.append({"case": "education", "rows": len(df), "seconds": time.perf_counter()-start,
                "checks": {"unique_student_id": bool(df.student_id.is_unique), "passed_within_attempted": bool((df.credits_passed <= df.credits_attempted).all()), "fraction_within_0_1": bool(df.completion_fraction.between(0, 1).all())}})

start = time.perf_counter()
temperature = np.zeros(1000)
temperature[0] = 20
for i in range(1, 1000):
    temperature[i] = np.clip(20 + .9*(temperature[i-1]-20) + rng.normal(0, .3), 10, 30)
df = pd.DataFrame({"sensor_id": "SENSOR-001", "timestamp": pd.date_range("2026-01-01", periods=1000, freq="min"), "temperature_c": temperature})
df.to_csv(OUT / "sensor.csv", index=False)
results.append({"case": "sensor_scenario", "rows": len(df), "seconds": time.perf_counter()-start,
                "checks": {"increasing_time": bool(df.timestamp.is_monotonic_increasing), "temperature_within_bounds": bool(df.temperature_c.between(10, 30).all())},
                "observed_lag1_correlation": float(df.temperature_c.autocorr())})

(OUT / "metrics.json").write_text(json.dumps({"seed": 2026, "evidence_status": "Executed scenario examples; not learned from real domain data; no domain-realism claim", "results": results}, indent=2))
assert all(all(x["checks"].values()) for x in results)
print(json.dumps(results, indent=2))
