import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.corpus import corpus_stats
from app.eval_runner import run_comparison
from app.model_catalog import CATALOG
from app.schemas import RunRequest
from app.storage import list_runs, load_run

app = FastAPI(title="doctl issue-classification eval harness")

# The frontend is served from this same FastAPI process (see the StaticFiles
# mount below) so it never needs cross-origin access — CORS here only matters
# for a local Vite dev server hitting a locally-run backend. Deliberately NOT
# a wildcard: this app is deployed publicly with a real, billed SI API key
# behind POST /api/jobs (unauthenticated by design, per the exercise's "runnable
# app" requirement), and a wildcard origin would let any web page's JS drive
# billed jobs using a visitor's browser as the vector.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# job_id -> {"status": "running"|"done"|"error", "run_id": str | None, "error": str | None}
_jobs: dict[str, dict] = {}

# POST /api/jobs has no auth (see CORS comment above) and every job spends real
# SI credits. This in-process lock caps worst-case exposure to one concurrent
# job at a time — combined with schemas.py's concurrency/limit/model bounds,
# that's a small, fixed ceiling on unattended spend rather than an unbounded one.
_job_in_flight = False


@app.get("/api/health")
def health():
    return {"status": "ok", "read_only": settings.hosted_demo_read_only}


@app.get("/api/models")
def models():
    return {"models": list(CATALOG.keys())}


@app.get("/api/corpus")
def corpus():
    return corpus_stats()


@app.get("/api/runs")
def runs():
    return {"runs": list_runs()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    result = load_run(run_id)
    if result is None:
        raise HTTPException(404, f"No run with id {run_id}")
    return result


async def _execute(job_id: str, request: RunRequest):
    global _job_in_flight
    try:
        result = await run_comparison(request)
        _jobs[job_id] = {"status": "done", "run_id": result.run_id, "error": None}
    except Exception as exc:  # noqa: BLE001 — surfaced to the polling client, not swallowed
        _jobs[job_id] = {"status": "error", "run_id": None, "error": str(exc)}
    finally:
        _job_in_flight = False


@app.post("/api/jobs")
def start_job(request: RunRequest, background_tasks: BackgroundTasks):
    global _job_in_flight
    if settings.hosted_demo_read_only:
        raise HTTPException(
            403,
            "This hosted demo is read-only and serves the real persisted "
            "mistral-3-14B vs deepseek-4-flash result. To run a live "
            "comparison against your own DigitalOcean SI API key, run the "
            "container locally — see the README's \"Run it yourself\" section.",
        )
    if _job_in_flight:
        raise HTTPException(429, "A comparison run is already in progress — wait for it to finish before starting another (each run spends real API credits).")
    _job_in_flight = True
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "run_id": None, "error": None}
    background_tasks.add_task(_execute, job_id, request)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"No job with id {job_id}")
    return job


# Serve the built frontend as static files in the single-container deployment.
# In local dev the frontend runs on its own Vite server instead, so this directory
# won't exist — the app is equally runnable either way.
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
