"""Find a model's real throughput ceiling by ramping concurrency, rather than
assuming per-call p50/p95 latency tells you the whole story.

Smaller/cheaper models commonly get much higher RPM/TPM ceilings than flagship
models on the same provider — for a "high volume across many repos" workload,
the binding constraint is often the rate limit, not how fast any single call
returns. This is a load-test, so it's deliberately scoped to ONE model per run
(not all 6 shortlisted models automatically) — run it against whichever model(s)
are still in contention once the accuracy/cost screening narrows things down,
not as a blanket up-front cost.

Usage:
    python3 scripts/probe_rate_limits.py --model openai-gpt-oss-20b
    python3 scripts/probe_rate_limits.py --model openai-gpt-oss-20b --levels 4,8,16,32
"""
import argparse
import asyncio
import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.corpus import load_corpus  # noqa: E402
from app.inference_client import InferenceClient  # noqa: E402

CALLS_PER_LEVEL = 40


async def probe_level(client: InferenceClient, model_id: str, issues, concurrency: int) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    issue_cycle = list(itertools.islice(itertools.cycle(issues), CALLS_PER_LEVEL))

    async def _bounded(issue):
        async with semaphore:
            return await client.classify_issue(issue, model_id)

    start = time.monotonic()
    results = await asyncio.gather(*(_bounded(i) for i in issue_cycle))
    wall_clock_s = time.monotonic() - start

    rate_limited = sum(1 for r in results if r.error_type == "rate_limit")
    other_errors = sum(1 for r in results if r.error_type not in ("none",))
    return {
        "concurrency": concurrency,
        "throughput_rps": len(results) / wall_clock_s,
        "wall_clock_s": wall_clock_s,
        "rate_limited": rate_limited,
        "other_errors": other_errors,
        "total_calls": len(results),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--levels", default="4,8,16,32", help="comma-separated concurrency levels to try, ascending")
    args = parser.parse_args()

    levels = [int(x) for x in args.levels.split(",")]
    issues = load_corpus()[:100]  # small pool, cycled — this is a throughput probe, not an accuracy eval

    client = InferenceClient()
    print(f"Probing {args.model} at concurrency levels {levels} ({CALLS_PER_LEVEL} calls/level)\n")
    try:
        for concurrency in levels:
            result = await probe_level(client, args.model, issues, concurrency)
            print(
                f"concurrency={result['concurrency']:>3}  "
                f"throughput={result['throughput_rps']:.2f} req/s  "
                f"rate_limited={result['rate_limited']}/{result['total_calls']}  "
                f"other_errors={result['other_errors']}/{result['total_calls']}  "
                f"wall_clock={result['wall_clock_s']:.1f}s"
            )
            if result["rate_limited"] > result["total_calls"] * 0.1:
                print(
                    f"  -> >10% rate-limited at concurrency={concurrency}; "
                    f"this is close to the real ceiling, stopping the ramp early."
                )
                break
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
