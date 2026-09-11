import asyncio
import time

from app.corpus import load_corpus
from app.inference_client import InferenceClient
from app.metrics import agreement_rate, summarize_model_run
from app.schemas import ClassificationResult, Issue, RunRequest, RunResult
from app.storage import new_run_id, save_run


async def _run_model(client: InferenceClient, model_id: str, issues: list[Issue], concurrency: int) -> tuple[list[ClassificationResult], float]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(issue: Issue) -> ClassificationResult:
        async with semaphore:
            return await client.classify_issue(issue, model_id)

    start = time.monotonic()
    results = await asyncio.gather(*(_bounded(issue) for issue in issues))
    wall_clock_s = time.monotonic() - start
    return list(results), wall_clock_s


def _merge_per_issue_rows(
    issues: list[Issue],
    results_a: list[ClassificationResult],
    results_b: list[ClassificationResult],
) -> list[dict]:
    by_number_a = {r.issue_number: r for r in results_a}
    by_number_b = {r.issue_number: r for r in results_b}
    rows = []
    for issue in issues:
        ra, rb = by_number_a.get(issue.number), by_number_b.get(issue.number)
        rows.append(
            {
                "number": issue.number,
                "title": issue.title,
                "html_url": issue.html_url,
                "ground_truth_label": issue.ground_truth_label,
                "ground_truth_source": issue.ground_truth_source,
                "model_a_label": ra.predicted_label if ra else None,
                "model_a_raw_output": ra.raw_output if ra else None,
                "model_a_error_type": ra.error_type if ra else None,
                "model_b_label": rb.predicted_label if rb else None,
                "model_b_raw_output": rb.raw_output if rb else None,
                "model_b_error_type": rb.error_type if rb else None,
                # Both predicted_label values must be present and equal — two
                # failed calls (both None) must never read as "agreement".
                "models_agree": bool(
                    ra and rb and ra.predicted_label is not None and ra.predicted_label == rb.predicted_label
                ),
            }
        )
    return rows


async def run_comparison(request: RunRequest) -> RunResult:
    all_issues = load_corpus()
    issues = all_issues[: request.limit] if request.limit else all_issues
    lookup = {i.number: i for i in issues}

    client = InferenceClient()
    try:
        (results_a, wall_a), (results_b, wall_b) = await asyncio.gather(
            _run_model(client, request.model_a, issues, request.concurrency),
            _run_model(client, request.model_b, issues, request.concurrency),
        )
    finally:
        await client.close()

    summary_a = summarize_model_run(request.model_a, results_a, lookup, request.concurrency, wall_a)
    summary_b = summarize_model_run(request.model_b, results_b, lookup, request.concurrency, wall_b)
    agree_rate, agree_excluded = agreement_rate(results_a, results_b)

    result = RunResult(
        run_id=new_run_id(),
        request=request,
        model_a_summary=summary_a,
        model_b_summary=summary_b,
        agreement_rate=agree_rate,
        agreement_excluded_count=agree_excluded,
        per_issue=_merge_per_issue_rows(issues, results_a, results_b),
    )
    save_run(result)
    return result
