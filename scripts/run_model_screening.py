"""Broader model-selection screening pass.

Runs each shortlisted open-weight model against the SCORED subset only (301
issues, not the full 536) — this is a cheap "which of these are even viable"
pass, not the final production comparison. The two models that come out ahead
on the accuracy/cost/latency/reasoning tradeoff go on to the real full-corpus
comparison, run through the actual app (see README for that split).

Results are written to disk incrementally, one model at a time, so a crash or
interrupt partway through a run doesn't lose the models that already finished
(and doesn't require re-paying for their calls on a retry — real SI credits
are spent per call, not per script invocation).

Usage:
    python3 scripts/run_model_screening.py                 # full screening run
    python3 scripts/run_model_screening.py --limit 5        # smoke test: first 5 scored issues
    python3 scripts/run_model_screening.py --limit 5 --model openai-gpt-oss-20b  # single model, single smoke test
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.corpus import load_corpus  # noqa: E402
from app.eval_runner import _run_model  # noqa: E402
from app.inference_client import InferenceClient  # noqa: E402
from app.metrics import summarize_model_run  # noqa: E402
from app.model_catalog import CATALOG  # noqa: E402

CONCURRENCY = 10
OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "model_screening_results.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only run the first N scored issues (for a cheap smoke test before the full run).",
    )
    parser.add_argument(
        "--model", action="append", dest="models", default=None,
        help="Only run this model_id (repeatable). Defaults to every model in CATALOG.",
    )
    return parser.parse_args()


def _load_existing_results() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text())
    return {}


def _write_results(results: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, indent=2))


async def main() -> None:
    args = parse_args()
    model_ids = args.models if args.models else list(CATALOG)
    unknown = [m for m in model_ids if m not in CATALOG]
    if unknown:
        raise SystemExit(f"Unknown model_id(s) not in CATALOG: {unknown}")

    all_issues = load_corpus()
    scored_issues = [i for i in all_issues if i.ground_truth_label is not None]
    if args.limit:
        scored_issues = scored_issues[: args.limit]
    lookup = {i.number: i for i in scored_issues}

    mode = f"SMOKE TEST (--limit {args.limit})" if args.limit else "FULL SCREENING RUN"
    print(f"{mode}: {len(model_ids)} model(s) against {len(scored_issues)} scored issues each.\n")

    # Incremental persistence: start from whatever's already on disk (e.g. a
    # prior interrupted run) so a re-run only needs --model for the ones that
    # didn't finish, rather than re-spending on every model from scratch.
    results = _load_existing_results()

    client = InferenceClient()
    try:
        for model_id in model_ids:
            print(f"--- {model_id} ---")
            t0 = time.monotonic()
            model_results, wall_clock_s = await _run_model(client, model_id, scored_issues, CONCURRENCY)
            for r in model_results:
                if r.error_type != "none":
                    print(f"    [{r.error_type}] issue #{r.issue_number}: {r.error_message}")
            summary = summarize_model_run(model_id, model_results, lookup, CONCURRENCY, wall_clock_s)
            results[model_id] = summary.model_dump()
            _write_results(results)
            print(
                f"  accuracy={summary.accuracy:.1%}  "
                f"cost_total=${summary.total_cost_usd:.4f}  "
                f"cost/correct=${(summary.cost_per_correct_classification_usd or 0):.5f}  "
                f"p50={summary.latency.p50_ms:.0f}ms  p95={summary.latency.p95_ms:.0f}ms  "
                f"errors={summary.errors.model_dump()}  "
                f"elapsed={time.monotonic() - t0:.0f}s"
            )
            print(f"  (written to {OUT_PATH})\n")
    finally:
        await client.close()

    print(f"Done. Results for {len(results)} model(s) in {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
