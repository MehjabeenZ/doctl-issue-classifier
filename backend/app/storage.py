import json
import time
from pathlib import Path

from app.config import settings
from app.schemas import RunResult

RUNS_DIR = Path(settings.data_dir) / "runs"


def save_run(result: RunResult) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{result.run_id}.json").write_text(result.model_dump_json(indent=2))


def load_run(run_id: str) -> RunResult | None:
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    return RunResult.model_validate_json(path.read_text())


def list_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    out = []
    for path in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text())
        out.append(
            {
                "run_id": data["run_id"],
                "model_a": data["request"]["model_a"],
                "model_b": data["request"]["model_b"],
                "concurrency": data["request"]["concurrency"],
            }
        )
    return out


def new_run_id() -> str:
    return f"run_{int(time.time())}"
