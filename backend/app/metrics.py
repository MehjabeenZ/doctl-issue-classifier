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
        # True per-class ground-truth counts, independent of whether a prediction
        # ever came back — a failed call still "used up" one of that class's
        # instances and must still count toward its support/recall.
        support_counts: dict[str, int] = {label: 0 for label in LABELS}
        for r in scored:
            true_label = issues_by_number[r.issue_number].ground_truth_label
            assert true_label is not None  # guaranteed by the `scored` filter above
            support_counts[true_label] += 1
            # A failed call (rate limit / timeout / parse error / any "other" error
            # type) produced no prediction at all — it must count against accuracy
            # (never marked correct, see below) but must NOT be written into the
            # confusion matrix as a prediction of the "other" *class*. Doing that
            # would misattribute an infrastructure failure to a real classification
            # choice, and would make a failed call on a genuinely `other`-labeled
            # issue look coincidentally "correct" the moment a future ground-truth
            # set ever includes that class. Failures simply don't appear in the
            # matrix at all; `support_counts` (not the matrix) is what accounts for
            # them in recall.
            if r.predicted_label is not None:
                confusion[true_label][r.predicted_label] += 1
                if r.predicted_label == true_label:
                    correct += 1
        accuracy = correct / len(scored)

        for label in LABELS:
            tp = confusion[label][label]
            fp = sum(confusion[t][label] for t in LABELS if t != label)
            support = support_counts[label]

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


def agreement_rate(results_a: list[ClassificationResult], results_b: list[ClassificationResult]) -> tuple[float, int]:
    """Returns (rate, excluded_count).

    An issue where either model failed to produce a prediction (rate limit,
    timeout, parse error, ...) is excluded from both the numerator and the
    denominator entirely — two `None`s must never count as the models
    "agreeing," which is what a naive `a.predicted_label == b.predicted_label`
    comparison would do. `excluded_count` is surfaced so the UI can show how
    many issues the headline rate is actually silent on, rather than hiding it.
    """
    by_number_b = {r.issue_number: r.predicted_label for r in results_b}
    comparable = []
    excluded = 0
    for r in results_a:
        if r.issue_number not in by_number_b:
            continue
        b_label = by_number_b[r.issue_number]
        if r.predicted_label is None or b_label is None:
            excluded += 1
            continue
        comparable.append((r.predicted_label, b_label))

    if not comparable:
        return 0.0, excluded
    agree = sum(1 for a_label, b_label in comparable if a_label == b_label)
    return agree / len(comparable), excluded
