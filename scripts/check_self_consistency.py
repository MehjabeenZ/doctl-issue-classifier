"""Self-consistency check: does a model give the same label for the same issue
across repeated identical calls, even at temperature=0?

temperature=0 is not a determinism guarantee (MoE routing, batching, and kernel
non-associativity all introduce variance) — for a 6-way label with real downstream
consequences, a model flip-flopping on identical input is a correctness bug, not a
style footnote. This is cheap to check (a small sample x a few repeats) and is run
separately from the main screening pass because it answers a different question
("is this model's output stable?") than accuracy does ("is this model's output right?").

Usage:
    python3 scripts/check_self_consistency.py                          # all 6 shortlisted models
    python3 scripts/check_self_consistency.py --model mistral-3-14B --model deepseek-4-flash
"""
import argparse
import asyncio
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.corpus import load_corpus  # noqa: E402
from app.inference_client import InferenceClient  # noqa: E402
from app.model_catalog import CATALOG  # noqa: E402

N_ISSUES = 30
N_REPEATS = 3
CONCURRENCY = 10
OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "self_consistency_results.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", action="append", dest="models", default=None,
        help="Only check this model_id (repeatable). Defaults to every model in CATALOG.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    model_ids = args.models if args.models else list(CATALOG)
    unknown = [m for m in model_ids if m not in CATALOG]
    if unknown:
        raise SystemExit(f"Unknown model_id(s) not in CATALOG: {unknown}")

    random.seed(7)
    issues = load_corpus()
    sample = random.sample(issues, N_ISSUES)

    print(
        f"Self-consistency check: {len(model_ids)} model(s) x {N_ISSUES} issues x "
        f"{N_REPEATS} repeats = {len(model_ids) * N_ISSUES * N_REPEATS} calls total.\n"
    )

    client = InferenceClient()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    all_results = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else {}

    async def _bounded_call(issue, model_id):
        async with semaphore:
            return await client.classify_issue(issue, model_id)

    try:
        for model_id in model_ids:
            t0 = time.monotonic()
            tasks = [
                _bounded_call(issue, model_id)
                for issue in sample
                for _ in range(N_REPEATS)
            ]
            results = await asyncio.gather(*tasks)

            # group results back by issue (N_REPEATS consecutive entries per issue)
            per_issue = {}
            for i, issue in enumerate(sample):
                repeats = results[i * N_REPEATS : (i + 1) * N_REPEATS]
                labels = [r.predicted_label for r in repeats]
                per_issue[issue.number] = labels

            unanimous = sum(1 for labels in per_issue.values() if len(set(labels)) == 1)
            majority = sum(
                1 for labels in per_issue.values()
                if Counter(labels).most_common(1)[0][1] > len(labels) / 2
            )
            total_cost = sum(r.cost_usd for r in results)

            all_results[model_id] = {
                "unanimous_rate": unanimous / len(sample),
                "majority_rate": majority / len(sample),
                "per_issue_labels": {str(k): v for k, v in per_issue.items()},
                "total_cost_usd": total_cost,
            }
            print(
                f"{model_id}: unanimous={unanimous}/{len(sample)} "
                f"({unanimous/len(sample):.0%})  majority={majority}/{len(sample)} "
                f"({majority/len(sample):.0%})  cost=${total_cost:.4f}  "
                f"elapsed={time.monotonic()-t0:.0f}s"
            )
            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUT_PATH.write_text(json.dumps(all_results, indent=2))
    finally:
        await client.close()

    print(f"\nWrote results for {len(all_results)} model(s) to {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
