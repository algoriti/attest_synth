"""Verify deliverable integrity without retraining generators or models."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator
from run_benchmark import datasets, SEEDS, ENGINES

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "benchmarks"
checks = []

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

for item in json.loads((BASE / "data/manifest.json").read_text()):
    check("primary input hash: " + item["member"], hashlib.sha256((BASE / "data" / item["member"]).read_bytes()).hexdigest() == item["csv_sha256"])

schema = json.loads((ROOT / "specification/synthetic-data-spec.schema.json").read_text())
Draft202012Validator.check_schema(schema)
for example in json.loads((ROOT / "specification/examples.json").read_text()):
    Draft202012Validator(schema).validate(example)
    cols = {c["name"] for c in example["columns"]}
    check("unique example columns: " + example["name"], len(cols) == len(example["columns"]))
    for c in example["columns"]:
        check("consistent bounds: " + example["name"] + "/" + c["name"], c.get("minimum", -float("inf")) <= c.get("maximum", float("inf")))
    for rule in example["constraints"]:
        check("known constraint columns: " + example["name"], set(rule["columns"]).issubset(cols))
        check("operator arity: " + example["name"], len(rule["columns"]) == {"unique": 1, "less_or_equal": 2, "product_equals": 3}[rule["operator"]])
    if "target" in example["evaluation"]:
        check("known evaluation target: " + example["name"], example["evaluation"]["target"] in cols)
    check("example mode/source: " + example["name"], (example["mode"] == "schema_rules") == (example["source"]["kind"] == "none"))

metrics = pd.read_csv(BASE / "results/metrics.csv")
check("all 54 runs succeeded", len(metrics) == 54 and metrics.status.eq("ok").all())
check("unique run identifiers", not metrics.duplicated(["dataset", "seed", "engine"]).any())
env = json.loads((BASE / "results/environment.json").read_text())
check("executed script hash unchanged", hashlib.sha256((BASE / "run_benchmark.py").read_bytes()).hexdigest() == env["script_sha256"])
summary = json.loads((BASE / "results/dataset_summary.json").read_text())
for name, df, target, task, cats, info in datasets():
    check("dataset dimensions: " + name, len(df) == summary[name]["benchmark_rows"])
    for seed in SEEDS:
        previous_split = None
        for engine in ["real_train_reference"] + ENGINES:
            work = BASE / "results/runs" / f"{name}_{seed}_{engine}"
            split = json.loads((work / "split.json").read_text())
            train_ids, test_ids = set(split["train_source_indices"]), set(split["test_source_indices"])
            check("disjoint complete split: " + work.name, not train_ids.intersection(test_ids) and train_ids.union(test_ids) == set(df.index))
            if previous_split is not None:
                check("paired split across engines: " + work.name, split == previous_split)
            previous_split = split
            train = df.iloc[split["train_source_indices"]]
            syn = pd.read_csv(work / "synthetic.csv")
            check("row count and columns: " + work.name, len(syn) == len(train) and list(syn) == list(train))
            check("finite/no missing output: " + work.name, not syn.isna().any().any() and np.isfinite(syn.select_dtypes(include="number").to_numpy()).all())
            for c in syn:
                if c in cats:
                    check("valid categories: " + work.name + "/" + c, syn[c].isin(train[c].unique()).all())
                else:
                    check("valid numeric bounds: " + work.name + "/" + c, syn[c].between(train[c].min()-1e-8, train[c].max()+1e-8).all())
                    if pd.api.types.is_integer_dtype(train[c]):
                        check("valid integer field: " + work.name + "/" + c, np.allclose(syn[c], np.rint(syn[c])))
check("copy control has full measured overlap", metrics[metrics.engine == "bootstrap_control"].exact_train_row_fraction.eq(1).all())

for item in json.loads((ROOT / "evidence/repository_manifest.json").read_text()):
    directory = ROOT / "evidence" / item["repo"].replace("/", "__")
    for kind, filename in [("readme", "README.upstream"), ("license", "LICENSE.upstream")]:
        check("upstream hash: " + item["repo"] + "/" + kind, hashlib.sha256((directory / filename).read_bytes()).hexdigest() == item[kind]["sha256"])
for item in json.loads((ROOT / "evidence/source_manifest.json").read_text()):
    if "sha256" in item:
        f = ROOT / "evidence" / item["repo"].replace("/", "__") / item["path"]
        check("captured source hash: " + item["path"], hashlib.sha256(f.read_bytes()).hexdigest() == item["sha256"])
for item in json.loads((ROOT / "evidence/installed/manifest.json").read_text()):
    f = ROOT / "evidence/installed" / item["snapshot"]
    check("installed evidence hash: " + item["snapshot"], hashlib.sha256(f.read_bytes()).hexdigest() == item["sha256"])

rules = json.loads((BASE / "results/rule_examples/metrics.json").read_text())
check("three rule scenarios / eight checks", len(rules["results"]) == 3 and sum(len(r["checks"]) for r in rules["results"]) == 8 and all(all(r["checks"].values()) for r in rules["results"]))

# Verification file is an intentional forward link while this script is running.
verification = BASE / "results/verification.json"
for f in ROOT.rglob("*.md"):
    text = f.read_text()
    for label, destination in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
        if destination.startswith(("http:", "https:", "#", "mailto:")):
            continue
        path = unquote(destination.split("#")[0].strip("<>"))
        target_path = (f.parent / path).resolve()
        check("local link: " + str(f.relative_to(ROOT)) + ":" + label, target_path.exists() or target_path == verification)
    definitions = set(re.findall(r"^\[([PTND]\d+)\]:", text, re.MULTILINE))
    used = set(re.findall(r"\[([PTND]\d+)\](?![:(])", text))
    check("source references resolve: " + str(f.relative_to(ROOT)), used.issubset(definitions))

verification.write_text(json.dumps({"verified_utc": datetime.now(timezone.utc).isoformat(), "status": "passed", "checks_passed": len(checks), "checks": checks}, indent=2))
print(f"PASS: {len(checks)} integrity, split, output, example and document checks; no model retraining.")
