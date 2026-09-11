"""Split the raw issue corpus into ground-truth construction tiers.

Tier logic (see README methodology section for the reasoning):
  - RULE_MAPPED: issue has exactly one category signal among doctl's real labels,
    mapped onto the 6-class schema. Treated as candidate (not final) ground truth.
  - VALIDATION_SAMPLE: a stratified-by-class sample drawn from RULE_MAPPED, with all
    labels stripped, used as a blind check on whether the rule mapping actually holds up.
  - NEEDS_LABELING: everything else (no category signal, or conflicting category
    labels) — genuinely needs a judgment call, not just a lookup.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

RAW_PATH = Path(__file__).parent.parent / "data" / "raw" / "issues.json"
OUT_DIR = Path(__file__).parent.parent / "data" / "processed"

# doctl's real labels that carry a usable category signal, mapped onto the customer's
# 6-class schema. Everything else is a meta label (platform, process, bot bookkeeping)
# and carries no category information on its own.
LABEL_TO_CLASS = {
    "bug": "bug",
    "security vulnerability": "security",
    "question": "question",
    "docs": "documentation",
    "suggestion": "enhancement",
    "enhancement": "enhancement",
    "api-parity": "enhancement",
}

VALIDATION_SAMPLE_PER_CLASS = 10  # ~50-60 issues total, stratified across 6 classes


def classify_by_rule(labels: list[str]) -> str | None:
    mapped = {LABEL_TO_CLASS[l] for l in labels if l in LABEL_TO_CLASS}
    if len(mapped) == 1:
        return next(iter(mapped))
    return None  # zero or conflicting signal


def main() -> None:
    issues = json.loads(RAW_PATH.read_text())

    rule_mapped = []
    needs_labeling = []

    for issue in issues:
        cls = classify_by_rule(issue["labels"])
        if cls is not None:
            rule_mapped.append({**issue, "rule_label": cls})
        else:
            needs_labeling.append(issue)

    # Stratified blind validation sample, labels stripped entirely.
    by_class = defaultdict(list)
    for issue in rule_mapped:
        by_class[issue["rule_label"]].append(issue)

    random.seed(42)  # reproducible sample across runs
    validation_sample = []
    validation_answer_key = {}
    for cls, items in by_class.items():
        k = min(VALIDATION_SAMPLE_PER_CLASS, len(items))
        picked = random.sample(items, k)
        for issue in picked:
            validation_answer_key[issue["number"]] = cls
            validation_sample.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": (issue["body"] or "")[:1500],
                    "state": issue["state"],
                    "html_url": issue["html_url"],
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "tier1_rule_mapped.json").write_text(
        json.dumps(
            [{"number": i["number"], "title": i["title"], "rule_label": i["rule_label"],
              "labels": i["labels"]} for i in rule_mapped],
            indent=2,
        )
    )
    (OUT_DIR / "validation_sample.json").write_text(json.dumps(validation_sample, indent=2))
    (OUT_DIR / "validation_answer_key.json").write_text(json.dumps(validation_answer_key, indent=2))
    (OUT_DIR / "needs_labeling.json").write_text(
        json.dumps(
            [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "body": (i["body"] or "")[:1500],
                    "state": i["state"],
                    "labels": i["labels"],
                    "html_url": i["html_url"],
                }
                for i in needs_labeling
            ],
            indent=2,
        )
    )

    print(f"Total issues:        {len(issues)}")
    print(f"Rule-mapped:         {len(rule_mapped)}")
    print(f"  by class:          {dict((k, len(v)) for k, v in by_class.items())}")
    print(f"Validation sample:   {len(validation_sample)} (blind, drawn from rule-mapped)")
    print(f"Needs labeling:      {len(needs_labeling)} (no signal or conflicting labels)")


if __name__ == "__main__":
    main()
