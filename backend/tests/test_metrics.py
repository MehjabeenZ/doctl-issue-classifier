from app.metrics import _percentile, agreement_rate, summarize_model_run
from app.schemas import ClassificationResult, Issue


def make_issue(number, gt_label=None):
    return Issue(number=number, title=f"issue {number}", body="", state="open", html_url="", ground_truth_label=gt_label)


def make_result(number, model_id, label, error_type="none"):
    return ClassificationResult(
        issue_number=number, model_id=model_id, predicted_label=label, raw_output="",
        input_tokens=100, output_tokens=5, cost_usd=0.001, latency_ms=100.0, attempts=1,
        error_type=error_type,
    )


def test_percentile_matches_known_values():
    values = sorted([100.0, 200.0, 300.0, 400.0, 500.0])
    assert _percentile(values, 0.0) == 100.0
    assert _percentile(values, 1.0) == 500.0
    assert _percentile(values, 0.5) == 300.0


def test_percentile_empty_list():
    assert _percentile([], 0.5) == 0.0


def test_summarize_model_run_accuracy_and_confusion():
    issues = {1: make_issue(1, "bug"), 2: make_issue(2, "bug"), 3: make_issue(3, "question")}
    results = [
        make_result(1, "m", "bug"),        # correct
        make_result(2, "m", "enhancement"), # wrong
        make_result(3, "m", "question"),   # correct
    ]
    summary = summarize_model_run("m", results, issues, concurrency=4, wall_clock_s=1.0)
    assert summary.accuracy == 2 / 3
    assert summary.confusion_matrix["bug"]["bug"] == 1
    assert summary.confusion_matrix["bug"]["enhancement"] == 1
    assert summary.confusion_matrix["question"]["question"] == 1


def test_zero_support_class_reports_none_not_zero():
    # No issue in the scored set has "documentation" as ground truth.
    issues = {1: make_issue(1, "bug")}
    results = [make_result(1, "m", "bug")]
    summary = summarize_model_run("m", results, issues, concurrency=4, wall_clock_s=1.0)
    assert summary.support_by_class["documentation"] == 0
    assert summary.recall_by_class["documentation"] is None
    assert summary.f1_by_class["documentation"] is None


def test_unparseable_prediction_counts_against_accuracy():
    issues = {1: make_issue(1, "bug")}
    results = [make_result(1, "m", None, error_type="parse_error")]
    summary = summarize_model_run("m", results, issues, concurrency=4, wall_clock_s=1.0)
    assert summary.accuracy == 0.0  # None predicted_label falls back to "other", not "bug"


def test_agreement_rate():
    results_a = [make_result(1, "a", "bug"), make_result(2, "a", "question")]
    results_b = [make_result(1, "b", "bug"), make_result(2, "b", "enhancement")]
    assert agreement_rate(results_a, results_b) == 0.5


def test_agreement_rate_no_overlap():
    assert agreement_rate([], []) == 0.0
