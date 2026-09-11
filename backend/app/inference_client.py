import random
import time

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.model_catalog import get_pricing
from app.prompt import STRUCTURED_OUTPUT_SCHEMA, SYSTEM_PROMPT, build_user_prompt, parse_label
from app.schemas import ClassificationResult, Issue


class RateLimitError(Exception):
    pass


class TransientServerError(Exception):
    pass


class StructuredOutputRejected(Exception):
    """The backend rejected response_format itself (a 400 on the very thing we're
    trying), distinct from the request just being malformed for some other reason."""


def _classify_http_error(exc: httpx.HTTPStatusError, structured_output_requested: bool) -> Exception:
    status = exc.response.status_code
    if status == 429:
        return RateLimitError(str(exc))
    if status >= 500:
        return TransientServerError(str(exc))
    if status == 400 and structured_output_requested:
        return StructuredOutputRejected(str(exc))
    raise exc  # 4xx other than the above is not retryable — a bad request stays a bad request


class InferenceClient:
    # Shared across the process/run — once a model 400s on response_format, every
    # subsequent call for that model skips straight to prompt-only, instead of
    # re-discovering the same rejection on every single one of its 500+ calls.
    _unsupported_structured_output: set[str] = set()

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.si_base_url,
            timeout=settings.request_timeout_s,
            headers={"Authorization": f"Bearer {settings.si_api_key}"},
        )

    async def close(self):
        await self._client.aclose()

    async def classify_issue(self, issue: Issue, model_id: str) -> ClassificationResult:
        if settings.dry_run:
            return await self._classify_dry_run(issue, model_id)

        attempts = 0
        start = time.monotonic()
        used_structured_output = model_id not in self._unsupported_structured_output

        @retry(
            reraise=True,
            stop=stop_after_attempt(settings.max_retries),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_s, min=1, max=20),
            retry=retry_if_exception_type((RateLimitError, TransientServerError, httpx.TimeoutException)),
        )
        async def _call(use_structured: bool):
            nonlocal attempts
            attempts += 1
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(issue.title, issue.body)},
                ],
                "temperature": 0,
                "max_tokens": settings.max_output_tokens,
            }
            if use_structured:
                payload["response_format"] = STRUCTURED_OUTPUT_SCHEMA
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                raise _classify_http_error(exc, use_structured) from exc

        try:
            try:
                data = await _call(used_structured_output)
            except StructuredOutputRejected:
                # One-time fallback: this model/backend doesn't honor response_format.
                # Remember it so we don't pay this discovery cost again this run.
                self._unsupported_structured_output.add(model_id)
                used_structured_output = False
                data = await _call(False)
        except RateLimitError as exc:
            return self._error_result(issue, model_id, attempts, "rate_limit", str(exc), start)
        except httpx.TimeoutException as exc:
            return self._error_result(issue, model_id, attempts, "timeout", str(exc), start)
        except Exception as exc:  # noqa: BLE001 — last-resort bucket, surfaced to the UI as "other"
            return self._error_result(issue, model_id, attempts, "other", str(exc), start)

        latency_ms = (time.monotonic() - start) * 1000
        choice = data["choices"][0]
        # Some reasoning models return content: null — either the reasoning consumed
        # the whole token budget before an answer, or the API splits chain-of-thought
        # into a separate field (e.g. reasoning_content) and leaves content empty.
        # Both are real, distinct-from-each-other failure modes worth naming, not an
        # AttributeError crash.
        raw_output = choice["message"].get("content") or ""
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        label = parse_label(raw_output)

        error_message = None
        if label is None:
            if not raw_output and finish_reason == "length":
                error_message = (
                    f"Empty content, finish_reason=length — model likely spent the "
                    f"full {settings.max_output_tokens}-token budget reasoning before answering."
                )
            else:
                error_message = f"Could not parse a label from: {raw_output[:200]!r} (finish_reason={finish_reason})"

        return ClassificationResult(
            issue_number=issue.number,
            model_id=model_id,
            predicted_label=label,
            raw_output=raw_output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=get_pricing(model_id).cost_usd(input_tokens, output_tokens),
            latency_ms=latency_ms,
            attempts=attempts,
            used_structured_output=used_structured_output,
            error_type="none" if label else "parse_error",
            error_message=error_message,
        )

    def _error_result(self, issue, model_id, attempts, error_type, message, start) -> ClassificationResult:
        return ClassificationResult(
            issue_number=issue.number,
            model_id=model_id,
            predicted_label=None,
            raw_output="",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=(time.monotonic() - start) * 1000,
            attempts=attempts,
            used_structured_output=False,
            error_type=error_type,
            error_message=message,
        )

    async def _classify_dry_run(self, issue: Issue, model_id: str) -> ClassificationResult:
        """Synthetic response so the harness, metrics, and UI are fully exercisable
        before real SI credits exist. Deliberately noisy (per-model accuracy, occasional
        errors, varied latency) rather than a clean pass-through of ground truth — a
        perfect-accuracy dry run wouldn't exercise the confusion-matrix off-diagonal,
        error views, or disagreement filters at all.
        """
        import asyncio
        from app.prompt import LABELS

        # Deterministic-ish per-model behavior so the two models look meaningfully
        # different in the demo, without hardcoding to any specific real model name.
        seed = sum(model_id.encode()) % 100
        accuracy_rate = 0.65 + (seed % 30) / 100  # spread across ~0.65-0.94
        base_latency_ms = 150 + (seed % 50) * 12  # spread across ~150-700ms
        error_rate = 0.02

        await asyncio.sleep(random.uniform(0.02, 0.08))  # keep dry runs fast regardless of simulated latency

        if random.random() < error_rate:
            error_type = random.choice(["rate_limit", "timeout", "other"])
            return self._error_result(
                issue, model_id, attempts=random.randint(1, 3), error_type=error_type,
                message=f"simulated {error_type} (dry run)", start=time.monotonic() - base_latency_ms / 1000,
            )

        true_label = issue.ground_truth_label
        if true_label and random.random() < accuracy_rate:
            label = true_label
        else:
            candidates = [l for l in LABELS if l != true_label] if true_label else LABELS
            label = random.choice(candidates)

        input_tokens, output_tokens = random.randint(180, 420), random.randint(6, 12)
        return ClassificationResult(
            issue_number=issue.number,
            model_id=model_id,
            predicted_label=label,
            raw_output=f'{{"label": "{label}"}}',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=get_pricing(model_id).cost_usd(input_tokens, output_tokens),
            latency_ms=max(50, random.gauss(base_latency_ms, base_latency_ms * 0.25)),
            attempts=1,
            used_structured_output=False,  # dry run never actually calls the API
            error_type="none",
            error_message=None,
        )
