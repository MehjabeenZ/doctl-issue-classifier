import json
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.schemas import Issue

DATA_DIR = Path(settings.data_dir)


@lru_cache(maxsize=1)
def load_corpus() -> list[Issue]:
    """Load the frozen issue snapshot and attach ground truth where it exists.

    Ground truth is optional at import time on purpose — the harness (and its dry-run
    mode) needs to be runnable before ground_truth.json is finalized.
    """
    raw = json.loads((DATA_DIR / "raw" / "issues.json").read_text())

    ground_truth_path = DATA_DIR / "processed" / "ground_truth.json"
    ground_truth: dict[str, dict] = {}
    if ground_truth_path.exists():
        ground_truth = {str(row["number"]): row for row in json.loads(ground_truth_path.read_text())}

    issues = []
    for item in raw:
        gt = ground_truth.get(str(item["number"]))
        issues.append(
            Issue(
                number=item["number"],
                title=item["title"],
                body=item["body"] or "",
                state=item["state"],
                html_url=item["html_url"],
                ground_truth_label=gt["label"] if gt else None,
                ground_truth_source=gt["source"] if gt else None,
            )
        )
    return issues


def issues_by_number() -> dict[int, Issue]:
    return {issue.number: issue for issue in load_corpus()}


def corpus_stats() -> dict:
    issues = load_corpus()
    scored = [i for i in issues if i.ground_truth_label is not None]
    from collections import Counter

    return {
        "total_issues": len(issues),
        "scored_count": len(scored),
        "unscored_count": len(issues) - len(scored),
        "scored_label_distribution": dict(Counter(i.ground_truth_label for i in scored)),
    }
