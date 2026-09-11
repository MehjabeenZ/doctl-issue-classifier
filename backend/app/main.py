import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.corpus import corpus_stats
from app.eval_runner import run_comparison
from app.model_catalog import CATALOG
from app.schemas import RunRequest
from app.storage import list_runs, load_run

app = FastAPI(title="doctl issue-classification eval harness")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# job_id -> {"status": "running"|"done"|"error", "run_id": str | None, "error": str | None}
_jobs: dict[str, dict] = {}


@app.get("/api/health")
def health():
    return {"status": "ok"}


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
    try:
        result = await run_comparison(request)
        _jobs[job_id] = {"status": "done", "run_id": result.run_id, "error": None}
    except Exception as exc:  # noqa: BLE001 — surfaced to the polling client, not swallowed
        _jobs[job_id] = {"status": "error", "run_id": None, "error": str(exc)}


@app.post("/api/jobs")
def start_job(request: RunRequest, background_tasks: BackgroundTasks):
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
