"""Reconcile the rule-mapped tier + two independent blind labelers into final ground truth.

Produces:
  - data/processed/ground_truth.json         final {number, label, source} for every
                                              issue that has a confident label
  - data/processed/needs_adjudication.json   remaining disagreements for a human read
  - prints an agreement-rate report (this IS the "how much do I trust maintainer
    labels / a single labeler" evidence for the README)
"""
from __future__ import annotations

import json
from pathlib import Path

PROC = Path(__file__).parent.parent / "data" / "processed"


def load(name):
    return json.loads((PROC / name).read_text())


def main():
    tier1 = load("tier1_rule_mapped.json")  # 301 issues, rule_label, has html_url? no, has labels
    validation_sample = load("validation_sample.json")  # 40 issues, blind
    validation_answer_key = load("validation_answer_key.json")  # number(str) -> rule_label
    needs_labeling = load("needs_labeling.json")  # 235 issues
    labeler_a = {row["number"]: row["label"] for row in load("labeler_a_output.json")}
    labeler_b = {row["number"]: row["label"] for row in load("labeler_b_output.json")}

    validation_numbers = {issue["number"] for issue in validation_sample}
    tier1_by_number = {issue["number"]: issue for issue in tier1}

    final = {}  # number -> {label, source}
    needs_adjudication = []

    # --- Validation tier: rule label vs 2 blind labelers -------------------------
    val_agree_all3 = val_majority = val_no_majority = 0
    for issue in validation_sample:
        n = issue["number"]
        rule_label = validation_answer_key[str(n)]
        a, b = labeler_a[n], labeler_b[n]
        votes = [rule_label, a, b]
        if rule_label == a == b:
            val_agree_all3 += 1
            final[n] = {"label": rule_label, "source": "validated_unanimous"}
        elif votes.count(rule_label) >= 2 or votes.count(a) >= 2 or votes.count(b) >= 2:
            val_majority += 1
            majority_label = max(set(votes), key=votes.count)
            final[n] = {"label": majority_label, "source": "validated_majority"}
        else:
            val_no_majority += 1
            needs_adjudication.append(
                {"number": n, "title": issue["title"], "body": issue["body"], "html_url": issue["html_url"],
                 "candidates": {"rule": rule_label, "labeler_a": a, "labeler_b": b}}
            )

    # --- Rule-mapped tier NOT in the validation sample: trust the rule -----------
    # (validated indirectly above — this is the tier the validation sample was drawn from)
    for n, issue in tier1_by_number.items():
        if n in validation_numbers:
            continue
        final[n] = {"label": issue["rule_label"], "source": "rule_mapped"}

    # --- Needs-labeling tier: 2 blind labelers, agree or adjudicate --------------
    needs_agree = needs_disagree = 0
    for issue in needs_labeling:
        n = issue["number"]
        a, b = labeler_a[n], labeler_b[n]
        if a == b:
            needs_agree += 1
            final[n] = {"label": a, "source": "double_labeled_agree"}
        else:
            needs_disagree += 1
            needs_adjudication.append(
                {"number": n, "title": issue["title"], "body": issue["body"], "html_url": issue["html_url"],
                 "candidates": {"labeler_a": a, "labeler_b": b}}
            )

    (PROC / "ground_truth.json").write_text(
        json.dumps([{"number": n, **v} for n, v in sorted(final.items())], indent=2)
    )
    (PROC / "needs_adjudication.json").write_text(json.dumps(needs_adjudication, indent=2))

    print("=== Validation tier (blind check on rule-mapped labels) ===")
    print(f"  unanimous (rule==A==B):     {val_agree_all3}/{len(validation_sample)}")
    print(f"  majority (2 of 3 agree):    {val_majority}/{len(validation_sample)}")
    print(f"  no majority (all differ):   {val_no_majority}/{len(validation_sample)}")
    print(f"  => rule-mapping agreement with independent reads: "
          f"{(val_agree_all3 + val_majority) / len(validation_sample):.0%}")
    print()
    print("=== Needs-labeling tier (2 independent blind labelers) ===")
    print(f"  agree:    {needs_agree}/{len(needs_labeling)} ({needs_agree/len(needs_labeling):.0%})")
    print(f"  disagree: {needs_disagree}/{len(needs_labeling)} ({needs_disagree/len(needs_labeling):.0%})")
    print()
    print(f"Final ground truth size: {len(final)}")
    print(f"Needs manual adjudication: {len(needs_adjudication)} (written to needs_adjudication.json)")

    from collections import Counter
    print(f"Final label distribution: {dict(Counter(v['label'] for v in final.values()))}")


if __name__ == "__main__":
    main()
