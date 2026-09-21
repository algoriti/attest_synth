"""HTTP API.

Generation runs in a background thread because ARF takes tens of seconds on a few
thousand rows, which is far too long to hold a request open. Jobs are therefore
created, polled and then collected.

State lives in memory for the proof of concept. Swapping `JOBS` and `UPLOADS` for
PostgreSQL tables is the obvious next step and touches nothing else.
"""
from __future__ import annotations

import io
import re
import hashlib
import math
import json
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .engines import available_engines
from .engines.relational import RelationalFeasibilityError
from .pipeline import PipelineError, run
from .profile import profile_csv
from .spec import SyntheticDataSpec
from .validator import validate

app = FastAPI(
    title="Synthetic Data Platform",
    version=__version__,
    description=(
        "Specification-driven synthetic data generation. The platform owns validation, "
        "provenance and evaluation; engines are replaceable workers."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE = Path(__file__).resolve().parents[1] / "storage"
STORAGE.mkdir(exist_ok=True)

UPLOADS: dict[str, dict[str, Any]] = {}
JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_JOB_SLOTS = threading.BoundedSemaphore(2)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def artifact_path(job_id: str, filename: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", job_id):
        raise HTTPException(400, "Invalid job identifier.")
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}\.(csv|json)", filename):
        raise HTTPException(400, "Invalid artifact name.")
    directory = (STORAGE / job_id).resolve()
    path = (directory / filename).resolve()
    if directory.parent != STORAGE.resolve() or path.parent != directory:
        raise HTTPException(400, "Artifact path is outside its job directory.")
    return path


# --- models ---------------------------------------------------------------------


class ValidateRequest(BaseModel):
    spec: dict


class GenerateRequest(BaseModel):
    spec: dict
    rows: int | None = Field(default=None, ge=1, le=200000)
    upload_id: str | None = None


# --- meta -----------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "time": _now()}


@app.get("/api/engines")
def engines() -> dict:
    """Every registered engine and exactly what it declares it can do."""
    return {"engines": available_engines()}


@app.get("/api/vocabulary")
def vocabulary() -> dict:
    """The closed vocabularies a form or an LLM must draw from."""
    from .spec import (
        ColumnType,
        ConstraintOperator,
        EXPR_OPS,
        Mode,
        Origin,
        Purpose,
        RuleKind,
        SemanticRole,
    )

    return {
        "modes": [m.value for m in Mode],
        "purposes": [p.value for p in Purpose],
        "roles": [
            {"value": r.value, "description": _ROLE_HELP[r.value]} for r in SemanticRole
        ],
        "column_types": [t.value for t in ColumnType],
        "rule_kinds": [k.value for k in RuleKind],
        "constraint_operators": [c.value for c in ConstraintOperator],
        "origins": [o.value for o in Origin],
        "expression_operators": sorted(EXPR_OPS),
    }


_ROLE_HELP = {
    "identifier": "Regenerated, never copied from the source.",
    "foreign_key": "Assigned from a declared parent relationship.",
    "learned": "A generator may model this column.",
    "rule": "Sampled from an explicit declared rule.",
    "derived": "Computed from other columns after generation.",
    "constant": "One value throughout.",
    "empty": "No observed values; emitted as null.",
    "aggregate": "Summarized from generated child records.",
}


# The assistant receives only an explicit user prompt, never an upload identifier.
class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=4000)


@app.get("/api/assistant/config")
def assistant_config():
    from .assistant import configuration
    return configuration()


@app.post("/api/assistant")
def assistant_proposal(request: AssistantRequest):
    from .assistant import propose
    try:
        return propose(request.prompt)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# --- upload and profiling --------------------------------------------------------


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a CSV and return a proposed specification plus a profiling report.

    Everything returned is a proposal. Nothing here is applied until it comes back in
    a specification that a person has reviewed.
    """
    if not file.filename or not file.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(400, "Upload a .csv file.")

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload a file smaller than 20 MB.")
    try:
        frame = pd.read_csv(io.BytesIO(raw), low_memory=False, sep="\t" if file.filename.lower().endswith(".tsv") else ",")
    except Exception as exc:
        raise HTTPException(400, f"Could not read the CSV: {exc}") from exc

    if frame.empty:
        raise HTTPException(400, "The uploaded file has no rows.")

    if len(frame) > 200000 or len(frame.columns) > 200:
        raise HTTPException(413, "Use at most 200,000 rows and 200 columns.")
    upload_id = uuid.uuid4().hex[:12]
    stem = Path(file.filename).stem.replace(" ", "_").replace("-", "_")[:40] or "uploaded"
    path = STORAGE / f"{upload_id}.csv"
    frame.to_csv(path, index=False)

    stem = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not stem or not stem[0].isalpha(): stem = "table_" + stem
    table, report = profile_csv(frame, stem, tz_offset_hours=0.0)

    with _LOCK:
        UPLOADS[upload_id] = {
            "filename": file.filename,
            "path": str(path),
            "rows": len(frame),
            "uploaded_utc": _now(),
        }

    return {
        "upload_id": upload_id,
        "filename": file.filename,
        "profile": report,
        "proposed_table": json.loads(table.model_dump_json()),
        "preview": _preview(frame),
    }


@app.post("/api/reprofile/{upload_id}")
def reprofile(upload_id: str, tz_offset_hours: float = 0.0) -> dict:
    """Re-run profiling with a different wall clock.

    Threshold rules such as "late after 07:45" are only discoverable when the local
    offset is right, so this is a first-class control rather than a setting.
    """
    frame = _load_upload(upload_id)
    stem = re.sub(r"[^A-Za-z0-9_]", "_", Path(UPLOADS[upload_id]["filename"]).stem)[:40] or "uploaded"
    if not stem[0].isalpha(): stem = "table_" + stem
    table, report = profile_csv(frame, stem, tz_offset_hours=tz_offset_hours)
    return {
        "upload_id": upload_id,
        "tz_offset_hours": tz_offset_hours,
        "profile": report,
        "proposed_table": json.loads(table.model_dump_json()),
    }


# --- validation ------------------------------------------------------------------


class SuggestRequest(BaseModel):
    spec: dict
    upload_id: str | None = None
    tz_offset_hours: float = 0.0
    accept: list[str] | None = None  # columns whose suggestions to apply


@app.post("/api/suggest")
def suggest_fixes(request: SuggestRequest) -> dict:
    """Propose deterministic rewrites for columns the chosen engine cannot model.

    With `accept`, returns the rewritten specification instead. Nothing is applied
    unless a caller names it: the rewrite is mechanical, but which features it keeps is
    a default rather than a finding, so a person has to take it.
    """
    from .engines import base as engine_base
    from .suggest import apply_suggestions, suggest_for_table

    try:
        spec = SyntheticDataSpec.model_validate(request.spec)
    except Exception as exc:
        raise HTTPException(422, f"The specification is not well formed: {exc}") from exc

    try:
        capabilities = engine_base.get_engine(engine_base.choose_engine(spec)).capabilities()
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc

    frame = None
    if request.upload_id:
        frame = _load_upload(request.upload_id)

    table = spec.primary_table
    suggestions = suggest_for_table(table, capabilities, request.tz_offset_hours, frame)

    if request.accept is None:
        return {
            "engine": capabilities["name"],
            "suggestions": [s.as_dict() for s in suggestions],
        }

    rewritten = apply_suggestions(table, suggestions, set(request.accept))
    spec.tables[0] = rewritten
    return {
        "engine": capabilities["name"],
        "applied": request.accept,
        "spec": json.loads(spec.model_dump_json()),
        "validation": validate(spec, capabilities).as_dict(),
    }


@app.post("/api/validate")
def validate_spec(request: ValidateRequest) -> dict:
    """Check a specification without generating anything."""
    try:
        spec = SyntheticDataSpec.model_validate(request.spec)
    except Exception as exc:
        return {
            "ok": False,
            "error_count": 1,
            "warning_count": 0,
            "findings": [
                {
                    "severity": "error",
                    "code": "schema_invalid",
                    "message": str(exc).split("\n")[0],
                    "scope": "",
                }
            ],
        }

    from .engines import base as engine_base

    engine_name = engine_base.choose_engine(spec)
    try:
        capabilities = engine_base.get_engine(engine_name).capabilities()
    except KeyError as exc:
        return {
            "ok": False,
            "error_count": 1,
            "warning_count": 0,
            "findings": [
                {"severity": "error", "code": "unknown_engine", "message": str(exc), "scope": ""}
            ],
        }

    result = validate(spec, capabilities).as_dict()
    result["spec"] = spec.model_dump(mode="json")
    result["engine"] = engine_name
    result["open_assumptions"] = spec.open_assumptions()
    return result


# --- generation ------------------------------------------------------------------


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict:
    """Start a generation job. Returns immediately with a job id."""
    try:
        spec = SyntheticDataSpec.model_validate(request.spec)
    except Exception as exc:
        raise HTTPException(422, f"The specification is not well formed: {exc}") from exc

    from .engines import base as engine_base
    try:
        caps = engine_base.get_engine(engine_base.choose_engine(spec)).capabilities()
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = validate(spec, caps)
    if not result.ok:
        raise HTTPException(422, result.as_dict())
    if not _JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Two jobs are already running. Wait for one to finish and retry.")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "slot_acquired": True,
            "spec_name": spec.name,
            "created_utc": _now(),
            "progress": "queued",
            # Surfaced so the generating screen can explain *why* it's slow instead
            # of leaving the person to guess: ARF on tens of thousands of rows
            # routinely takes minutes, and a bare spinner reads as a hang.
            "engine": engine_base.choose_engine(spec),
            "requested_rows": request.rows,
        }

    thread = threading.Thread(
        target=_run_job, args=(job_id, spec, request.rows, request.upload_id), daemon=True
    )
    thread.start()
    return {"job_id": job_id, "status": "queued"}


def _run_job(job_id: str, spec: SyntheticDataSpec, rows: int | None, upload_id: str | None) -> None:
    def note(stage: str) -> None:
        with _LOCK:
            JOBS[job_id]["progress"] = stage

    try:
        with _LOCK:
            JOBS[job_id]["status"] = "running"
        note("loading source")

        sources: dict[str, pd.DataFrame] = {}
        if upload_id:
            frame = _load_upload(upload_id)
            sources[spec.primary_table.name] = frame
            spec.primary_table.source.upload_id = upload_id

        note("generating")
        result = run(spec, sources=sources, rows=rows)

        result["report"] = _finite_json(result["report"])
        note("writing artefacts")
        out_dir = STORAGE / job_id
        out_dir.mkdir(exist_ok=True)
        previews = {}
        for name, frame in result["frames"].items():
            frame.to_csv(artifact_path(job_id, f"{name}.csv"), index=False)
            previews[name] = _preview(frame)
        (out_dir / "evidence_report.json").write_text(
            json.dumps(result["report"], indent=2, default=str)
        )
        (out_dir / "specification.json").write_text(json.dumps(result["report"]["reproduction"]["resolved_specification"], indent=2))
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_dir.iterdir() if p.is_file()}
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        with _LOCK:
            JOBS[job_id].update(
                {
                    "status": "completed",
                    "progress": "done",
                    "finished_utc": _now(),
                    "report": result["report"],
                    "previews": previews,
                    "tables": list(result["frames"]),
                }
            )
    except PipelineError as exc:
        with _LOCK:
            JOBS[job_id].update(
                {
                    "status": "rejected",
                    "progress": "rejected",
                    "error": str(exc),
                    "findings": exc.findings,
                    "finished_utc": _now(),
                }
            )
    except RelationalFeasibilityError as exc:
        # A declared row count or cardinality range that cannot be satisfied is a
        # fixable specification problem, not an engine crash — it should read like
        # one. Without this branch it fell through to the generic handler below and
        # reached the UI as "the engine failed" with a raw Python traceback for what
        # is really a rejected-before-generation message that just arrived a little
        # late, once the engine had already worked out the request was infeasible.
        with _LOCK:
            JOBS[job_id].update(
                {
                    "status": "rejected",
                    "progress": "rejected",
                    "error": str(exc),
                    "finished_utc": _now(),
                }
            )
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        with _LOCK:
            JOBS[job_id].update(
                {
                    "status": "failed",
                    "progress": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                    "finished_utc": _now(),
                }
            )

    finally:
        if JOBS.get(job_id, {}).pop("slot_acquired", False):
            _JOB_SLOTS.release()


@app.get("/api/jobs")
def list_jobs() -> dict:
    with _LOCK:
        rows = [
            {k: v for k, v in job.items() if k not in ("report", "previews", "traceback")}
            for job in JOBS.values()
        ]
    return {"jobs": sorted(rows, key=lambda j: j["created_utc"], reverse=True)}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    with _LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    return job


@app.get("/api/jobs/{job_id}/download/{table}")
def download(job_id: str, table: str):
    path = artifact_path(job_id, f"{table}.csv")
    if not path.exists():
        raise HTTPException(404, "No such table for this job.")
    return FileResponse(path, media_type="text/csv", filename=f"{table}.csv")


@app.get("/api/jobs/{job_id}/report")
def download_report(job_id: str):
    path = artifact_path(job_id, "evidence_report.json")
    if not path.exists():
        raise HTTPException(404, "No report for this job.")
    return FileResponse(path, media_type="application/json", filename="evidence_report.json")


@app.get("/api/jobs/{job_id}/specification")
def download_specification(job_id: str):
    """The specification that produced this dataset.

    The report says what happened; this is the artefact that reproduces it. Keeping it
    reachable only by digging through the storage directory made the reproducible part
    of the deliverable the hardest part to obtain.
    """
    path = artifact_path(job_id, "specification.json")
    if not path.exists():
        raise HTTPException(404, "No specification for this job.")
    return FileResponse(path, media_type="application/json", filename="specification.json")


# --- examples --------------------------------------------------------------------


@app.get("/api/examples")
def examples() -> dict:
    """Ready-made specifications, so the UI is never a blank page."""
    directory = Path(__file__).resolve().parents[1] / "specs"
    found = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = SyntheticDataSpec.model_validate_json(path.read_text()).model_dump(mode="json")
        except ValueError:
            continue
        found.append(
            {
                "id": path.stem,
                "name": payload.get("name", path.stem),
                "mode": payload.get("mode"),
                "purpose": payload.get("purpose"),
                "description": payload.get("description", ""),
                "spec": payload,
            }
        )
    return {"examples": found}


# --- helpers ---------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_upload(upload_id: str) -> pd.DataFrame:
    with _LOCK:
        record = UPLOADS.get(upload_id)
    if record is None:
        raise HTTPException(404, "Unknown upload id. Upload the CSV again.")
    return pd.read_csv(record["path"], low_memory=False)


def _preview(frame: pd.DataFrame, rows: int = 20) -> dict:
    head = frame.head(rows)
    return {
        "columns": list(frame.columns),
        "rows": json.loads(head.to_json(orient="records", date_format="iso")),
        "total_rows": int(len(frame)),
        "dtypes": {c: str(frame[c].dtype) for c in frame.columns},
    }


# --- static frontend --------------------------------------------------------------

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")


def _finite_json(value):
    if isinstance(value, np.generic): return _finite_json(value.item())
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, dict): return {k:_finite_json(v) for k,v in value.items()}
    if isinstance(value, list): return [_finite_json(v) for v in value]
    return value
