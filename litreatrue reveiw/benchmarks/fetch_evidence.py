"""Download public benchmark inputs and versioned upstream evidence; no credentials."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
REPOS = [
    "sdv-dev/Copulas", "DataResponsibly/DataSynthesizer", "vanderschaarlab/synthcity",
    "opendp/smartnoise-sdk", "sdv-dev/SDV", "sdv-dev/CTGAN", "sdv-dev/SDMetrics",
    "synthetichealth/synthea", "alan-turing-institute/tapas", "joke2k/faker",
    "worldbank/REaLTabFormer", "yandex-research/tab-ddpm", "tabularis-ai/be_great",
    "bips-hb/arfpy",
]

def get(url):
    r = requests.get(url, timeout=(10, 35), headers={"User-Agent": "synthetic-data-literature-review"})
    r.raise_for_status()
    return r

def repo_snapshot(repo):
    result = {"repo": repo, "accessed_utc": datetime.now(timezone.utc).isoformat()}
    try:
        meta = get(f"https://api.github.com/repos/{repo}").json()
        result.update({k: meta.get(k) for k in ["default_branch", "pushed_at", "archived", "license", "html_url"]})
        commit = get(f"https://api.github.com/repos/{repo}/commits/{meta['default_branch']}").json()
        result["commit"] = commit["sha"]
        result["commit_date"] = commit["commit"]["committer"]["date"]
        directory = ROOT / "evidence" / repo.replace("/", "__")
        directory.mkdir(parents=True, exist_ok=True)
        for kind in ["readme", "license"]:
            try:
                item = get(f"https://api.github.com/repos/{repo}/{kind}?ref={commit['sha']}").json()
                data = base64.b64decode(item["content"])
                (directory / ("README.upstream" if kind == "readme" else "LICENSE.upstream")).write_bytes(data)
                result[kind] = {"path": item["path"], "url": item["html_url"], "sha256": hashlib.sha256(data).hexdigest()}
            except Exception as e:
                result[kind + "_error"] = str(e)
    except Exception as e:
        result["error"] = str(e)
    print(json.dumps(result), flush=True)
    return result

def datasets():
    specs = [(222, "bank+marketing", "bank.csv"), (320, "student+performance", "student-mat.csv"), (186, "wine+quality", "winequality-red.csv")]
    results = []
    def find_member(blob, target):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for name in z.namelist():
                if Path(name).name == target:
                    return z.read(name)
            for name in z.namelist():
                if name.endswith(".zip"):
                    found = find_member(z.read(name), target)
                    if found is not None:
                        return found
        return None
    for ident, slug, member in specs:
        url = f"https://archive.ics.uci.edu/static/public/{ident}/{slug}.zip"
        item = {"url": url, "landing_page": f"https://archive.ics.uci.edu/dataset/{ident}/{slug}", "member": member, "license": "CC BY 4.0 (UCI landing page)", "accessed_utc": datetime.now(timezone.utc).isoformat()}
        try:
            blob = get(url).content
            item["archive_sha256"] = hashlib.sha256(blob).hexdigest()
            extracted = find_member(blob, member)
            if extracted is None:
                raise ValueError(f"Missing {member}")
            (ROOT / "benchmarks" / "data" / member).write_bytes(extracted)
            item["csv_sha256"] = hashlib.sha256(extracted).hexdigest()
            item["bytes"] = len(extracted)
        except Exception as e:
            item["error"] = str(e)
        print(json.dumps(item), flush=True)
        results.append(item)
    (ROOT / "benchmarks" / "data" / "manifest.json").write_text(json.dumps(results, indent=2))

def sources():
    manifests = {x["repo"]: x for x in json.loads((ROOT / "evidence/repository_manifest.json").read_text())}
    files = {
        "vanderschaarlab/synthcity": ["src/synthcity/plugins/core/plugin.py", "src/synthcity/plugins/core/dataloader.py", "src/synthcity/plugins/generic/plugin_ctgan.py", "setup.py"],
        "opendp/smartnoise-sdk": ["synth/snsynth/base.py", "synth/snsynth/mst/mst.py", "synth/snsynth/transform/table.py", "synth/pyproject.toml"],
        "worldbank/REaLTabFormer": ["realtabformer/realtabformer.py"],
    }
    results = []
    for repo, paths in files.items():
        for path in paths:
            sha = manifests[repo]["commit"]
            url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
            item = {"repo": repo, "commit": sha, "path": path, "url": url}
            try:
                blob = get(url).content
                dest = ROOT / "evidence" / repo.replace("/", "__") / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob)
                item["sha256"] = hashlib.sha256(blob).hexdigest()
            except Exception as e:
                item["error"] = str(e)
            results.append(item)
    (ROOT / "evidence/source_manifest.json").write_text(json.dumps(results, indent=2))
    metadata = []
    for package in ["synthcity", "smartnoise-synth", "DataSynthesizer", "arfpy", "copulas", "ctgan", "sdmetrics"]:
        try:
            data = get(f"https://pypi.org/pypi/{package}/json").json()
            metadata.append({"package": package, "version": data["info"]["version"], "requires_python": data["info"]["requires_python"], "requires_dist": data["info"]["requires_dist"], "release_files": [{k: x.get(k) for k in ["filename", "upload_time_iso_8601", "digests"]} for x in data["urls"]]})
        except Exception as e:
            metadata.append({"package": package, "error": str(e)})
    (ROOT / "evidence/pypi_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(results), flush=True)

if __name__ == "__main__":
    if "--sources" in sys.argv:
        sources()
        raise SystemExit(0)
    if "--datasets-only" in sys.argv:
        datasets()
        raise SystemExit(0)
    with ThreadPoolExecutor(max_workers=5) as pool:
        future = pool.submit(datasets)
        results = list(pool.map(repo_snapshot, REPOS))
        future.result()
    (ROOT / "evidence" / "repository_manifest.json").write_text(json.dumps(results, indent=2))
