"""Pull all issues (open + closed) from digitalocean/doctl and freeze a stable corpus snapshot.

Thin by design (see exercise spec: "a few hundred lines at most"). Run once; the output
JSON is the corpus everything else reads from, so re-runs of the eval harness never
depend on GitHub's live state (issues get relabeled, edited, or locked over time).

Usage:
    GITHUB_TOKEN=<optional> python scripts/ingest_issues.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

REPO = "digitalocean/doctl"
OUT_PATH = Path(__file__).parent.parent / "data" / "raw" / "issues.json"
PER_PAGE = 100


def fetch_all_issues(token: str | None) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    issues: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"https://api.github.com/repos/{REPO}/issues",
            headers=headers,
            params={"state": "all", "per_page": PER_PAGE, "page": page},
            timeout=30,
        )
        remaining = resp.headers.get("x-ratelimit-remaining")
        if resp.status_code == 403 and remaining == "0":
            reset = int(resp.headers.get("x-ratelimit-reset", time.time() + 60))
            wait = max(reset - time.time(), 1)
            print(f"Rate limited, sleeping {wait:.0f}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break

        # The GitHub issues endpoint also returns pull requests. The exercise scope
        # is issues, so PRs are dropped here rather than downstream.
        issues.extend(item for item in batch if "pull_request" not in item)

        print(f"page {page}: +{len(batch)} items ({len(issues)} issues so far)", file=sys.stderr)
        page += 1

    return issues


def slim(issue: dict) -> dict:
    """Keep only the fields the classifier and ground-truth pipeline actually use."""
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"] or "",
        "state": issue["state"],
        "labels": [label["name"] for label in issue["labels"]],
        "created_at": issue["created_at"],
        "closed_at": issue["closed_at"],
        "comments": issue["comments"],
        "html_url": issue["html_url"],
    }


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "No GITHUB_TOKEN set — using unauthenticated GitHub API (60 req/hr, "
            "fine for a one-time ~500-issue pull but slower if rate-limited).",
            file=sys.stderr,
        )

    issues = fetch_all_issues(token)
    slimmed = [slim(i) for i in issues]
    slimmed.sort(key=lambda i: i["number"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(slimmed, indent=2))
    print(f"Wrote {len(slimmed)} issues to {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
