import math
from collections import defaultdict

from app.prompt import LABELS
from app.schemas import ClassificationResult, ErrorBreakdown, Issue, LatencyStats, ModelRunSummary


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def summarize_model_run(
    model_id: str,
    results: list[ClassificationResult],
    issues_by_number: dict[int, Issue],
    concurrency: int,
    wall_clock_s: float,
) -> ModelRunSummary:
    total_calls = len(results)
    total_cost = sum(r.cost_usd for r in results)
    latencies = sorted(r.latency_ms for r in results)

    errors = ErrorBreakdown()
    for r in results:
        if r.error_type == "rate_limit":
            errors.rate_limit += 1
        elif r.error_type == "timeout":
            errors.timeout += 1
        elif r.error_type == "parse_error":
            errors.parse_error += 1
        elif r.error_type == "other":
            errors.other += 1

    scored = [r for r in results if issues_by_number[r.issue_number].ground_truth_label is not None]
    accuracy = None
    precision_by_class: dict[str, float | None] = {}
    recall_by_class: dict[str, float | None] = {}
    f1_by_class: dict[str, float | None] = {}
    support_by_class: dict[str, int] = {}
    confusion: dict[str, dict[str, int]] = {label: {l2: 0 for l2 in LABELS} for label in LABELS}
    correct = 0

    if scored:
        for r in scored:
            true_label = issues_by_number[r.issue_number].ground_truth_label
            pred_label = r.predicted_label or "other"  # unparseable output counts against accuracy, not silently dropped
            confusion[true_label][pred_label] += 1
            if pred_label == true_label:
                correct += 1
        accuracy = correct / len(scored)

        for label in LABELS:
            tp = confusion[label][label]
            fp = sum(confusion[t][label] for t in LABELS if t != label)
            fn = sum(confusion[label][p] for p in LABELS if p != label)
            support = tp + fn  # how many ground-truth instances of this class exist in the scored set

            # None (not 0.0) distinguishes "no data to score" from "model got it wrong every time"
            precision = tp / (tp + fp) if (tp + fp) else None  # model never predicted this class at all
            recall = tp / support if support else None  # class has zero ground-truth examples
            if precision is None or recall is None:
                f1 = None
            else:
                f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

            precision_by_class[label] = precision
            recall_by_class[label] = recall
            f1_by_class[label] = f1
            support_by_class[label] = support

    cost_per_correct = (total_cost / correct) if scored and correct else None

    suggestion_distribution: dict[str, int] = defaultdict(int)
    for r in results:
        suggestion_distribution[r.predicted_label or "unparseable"] += 1

    return ModelRunSummary(
        model_id=model_id,
        total_calls=total_calls,
        total_cost_usd=total_cost,
        cost_per_call_usd=(total_cost / total_calls) if total_calls else 0.0,
        cost_per_correct_classification_usd=cost_per_correct,
        latency=LatencyStats(
            p50_ms=_percentile(latencies, 0.50),
            p95_ms=_percentile(latencies, 0.95),
            concurrency_at_measurement=concurrency,
        ),
        wall_clock_s=wall_clock_s,
        throughput_rps=(total_calls / wall_clock_s) if wall_clock_s > 0 else 0.0,
        errors=errors,
        accuracy=accuracy,
        precision_by_class=precision_by_class,
        recall_by_class=recall_by_class,
        f1_by_class=f1_by_class,
        support_by_class=support_by_class,
        confusion_matrix=confusion,
        suggestion_distribution=dict(suggestion_distribution),
    )


def agreement_rate(results_a: list[ClassificationResult], results_b: list[ClassificationResult]) -> float:
    by_number_b = {r.issue_number: r.predicted_label for r in results_b}
    comparable = [r for r in results_a if r.issue_number in by_number_b]
    if not comparable:
        return 0.0
    agree = sum(1 for r in comparable if r.predicted_label == by_number_b[r.issue_number])
    return agree / len(comparable)
