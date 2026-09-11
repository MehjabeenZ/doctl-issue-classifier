import json
import re

LABELS = ["bug", "enhancement", "question", "documentation", "security", "other"]

SYSTEM_PROMPT = f"""You are classifying GitHub issues from the doctl repository (DigitalOcean's CLI) into exactly one category.

Categories:
- bug: something in doctl is broken or not working as expected.
- enhancement: a request for new functionality, an improvement, or a feature that doesn't exist yet.
- question: the author is asking how to do something or requesting help/clarification, not reporting a defect or requesting a feature.
- documentation: the issue is about documentation itself — missing, unclear, incorrect, or requested docs/help text/man pages/README/examples.
- security: a security vulnerability, CVE, or security-relevant concern about doctl or a dependency.
- other: genuinely doesn't fit any of the above (spam, duplicate, off-topic, or too ambiguous to classify).

Respond with ONLY a JSON object of the exact shape {{"label": "<one of: {', '.join(LABELS)}>"}}. No other text."""


def build_user_prompt(title: str, body: str) -> str:
    return f"Title: {title}\n\nBody:\n{body[:4000]}"


# Constrained-decoding structured output (OpenAI-compatible response_format).
# Tried first on every model — eliminates malformed-JSON failures at the source
# rather than catching them after the fact with the regex/bare-word fallback below.
# Not every model/backend behind DO's unified API necessarily honors this, so the
# inference client falls back to prompt-only + the parser below on a 400 and
# remembers not to retry it for that model for the rest of the run.
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "issue_classification",
        "schema": {
            "type": "object",
            "properties": {"label": {"type": "string", "enum": LABELS}},
            "required": ["label"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_JSON_LABEL_RE = re.compile(r'"label"\s*:\s*"(\w+)"')


def parse_label(raw_output: str) -> str | None:
    """Parse the model's raw output into one of LABELS, or None if unparseable.

    Tries strict JSON first, then falls back to a regex scrape (models don't always
    respect "no other text") and finally a bare-word match. Anything that fails all
    three is a parse_error, tracked separately from network-level failures.
    """
    text = raw_output.strip()

    try:
        parsed = json.loads(text)
        label = parsed.get("label", "").strip().lower()
        if label in LABELS:
            return label
    except (json.JSONDecodeError, AttributeError):
        pass

    match = _JSON_LABEL_RE.search(text)
    if match and match.group(1).lower() in LABELS:
        return match.group(1).lower()

    lowered = text.lower()
    for label in LABELS:
        if label in lowered:
            return label

    return None
