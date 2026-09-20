"""Fallback acquisition when UCI's download host is unreachable.

These are third-party dataset mirrors, NOT primary scientific evidence.
Commit, hash, shape, and provenance limits are recorded explicitly.
"""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
SPECS = [
    ("Jean-BaptisteAC/Customer-classification", "bank.csv", "bank.csv", 222),
    ("yogeshsachdeva223/Student_mat_exploration_and_visualisation", "student-mat.csv", "student-mat.csv", 320),
    ("jbrownlee/Datasets", "winequality-red.csv", "winequality-red.csv", 186),
]

def get(url):
    r = requests.get(url, timeout=(10, 30))
    r.raise_for_status()
    return r.json()

items = []
for repo, path, out, uci in SPECS:
    item = {"uci_id": uci, "primary_url": f"https://archive.ics.uci.edu/dataset/{uci}", "mirror": repo,
            "accessed_utc": datetime.now(timezone.utc).isoformat(),
            "provenance_note": "Third-party mirror; byte identity with unreachable UCI archive not verified. See UCI for original attribution and CC BY 4.0 terms."}
    try:
        # GitHub's unauthenticated API quota was exhausted by evidence snapshots.
        # Record a content hash instead of claiming a commit pin we could not fetch.
        for branch in ["main", "master"]:
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
            response = requests.get(url, timeout=(10, 30))
            if response.ok:
                break
        response.raise_for_status()
        blob = response.content
        item.update({"commit": None, "url": url, "download_sha256": hashlib.sha256(blob).hexdigest(), "version_note": "Mutable upstream branch; local bytes frozen by SHA256."})
        if uci == 186:
            df = pd.read_csv(io.BytesIO(blob), header=None)
            df.columns = ["fixed acidity", "volatile acidity", "citric acid", "residual sugar", "chlorides", "free sulfur dioxide", "total sulfur dioxide", "density", "pH", "sulphates", "alcohol", "quality"]
        else:
            df = pd.read_csv(io.BytesIO(blob), sep=None, engine="python")
        df.to_csv(ROOT / "data" / out, index=False)
        item.update({"file": out, "rows": len(df), "columns": list(df.columns), "csv_sha256": hashlib.sha256((ROOT / "data" / out).read_bytes()).hexdigest()})
    except Exception as e:
        item["error"] = str(e)
    items.append(item)
    print(json.dumps(item), flush=True)
(ROOT / "data" / "mirror_manifest.json").write_text(json.dumps(items, indent=2))
