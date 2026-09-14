from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.model_catalog import CATALOG

LabelClass = Literal["bug", "enhancement", "question", "documentation", "security", "other"]
ErrorType = Literal["rate_limit", "timeout", "parse_error", "other", "none"]

# Both requests hit a real, billed, per-token API. This app is deployed
# publicly with a live key and unauthenticated POST /api/jobs (see main.py's
# docstring note) — these bounds are the only thing standing between a random
# caller and an unbounded number of full-corpus runs. Pick numbers generous
# enough for legitimate use (RunControls.jsx's own UI caps concurrency at 64)
# but small enough that even a worst-case abusive call is cheap.
MAX_CONCURRENCY = 64
MAX_LIMIT = 536  # current corpus size; a generous fixed ceiling rather than importing corpus.py here


class APIModel(BaseModel):
    """Base for all schemas here — several fields are legitimately named model_*
    (it's a model-comparison app), which collides with pydantic's default
    protected-namespace guard unless disabled."""

    model_config = ConfigDict(protected_namespaces=())


class Issue(APIModel):
    number: int
    title: str
    body: str
    state: str
    html_url: str
    ground_truth_label: Optional[LabelClass] = None
    ground_truth_source: Optional[str] = None  # e.g. "rule_mapped", "manual_audit"


class ClassificationResult(APIModel):
    issue_number: int
    model_id: str
    predicted_label: Optional[LabelClass]
    raw_output: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    attempts: int
    used_structured_output: bool = False  # False = fell back to prompt-only parsing
    error_type: ErrorType = "none"
    error_message: Optional[str] = None


class RunRequest(APIModel):
    model_a: str
    model_b: str
    concurrency: int = 8
    limit: Optional[int] = None  # cap corpus size for quick smoke runs

    @field_validator("model_a", "model_b")
    @classmethod
    def _model_must_be_in_catalog(cls, v: str) -> str:
        if v not in CATALOG:
            raise ValueError(f"unknown model id {v!r} — must be one of the catalog models from GET /api/models")
        return v

    @field_validator("concurrency")
    @classmethod
    def _bound_concurrency(cls, v: int) -> int:
        if not (1 <= v <= MAX_CONCURRENCY):
            raise ValueError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")
        return v

    @field_validator("limit")
    @classmethod
    def _bound_limit(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= MAX_LIMIT):
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        return v


class LatencyStats(APIModel):
    p50_ms: float
    p95_ms: float
    concurrency_at_measurement: int


class ErrorBreakdown(APIModel):
    rate_limit: int = 0
    timeout: int = 0
    parse_error: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        return self.rate_limit + self.timeout + self.parse_error + self.other


class ModelRunSummary(APIModel):
    model_id: str
    total_calls: int
    total_cost_usd: float
    cost_per_call_usd: float
    cost_per_correct_classification_usd: Optional[float]
    latency: LatencyStats
    wall_clock_s: float
    throughput_rps: float
    errors: ErrorBreakdown

    # Scored-subset metrics (None if no ground truth available)
    accuracy: Optional[float] = None
    # None (not 0.0) when a class has zero ground-truth support in the scored set —
    # "no data" and "model scored zero" must never look the same in the UI.
    precision_by_class: dict[str, Optional[float]] = {}
    recall_by_class: dict[str, Optional[float]] = {}
    f1_by_class: dict[str, Optional[float]] = {}
    support_by_class: dict[str, int] = {}  # ground-truth count per class in the scored set
    confusion_matrix: dict[str, dict[str, int]] = {}  # {true_label: {pred_label: count}}

    # Unscored-view aggregate
    suggestion_distribution: dict[str, int] = {}


class RunResult(APIModel):
    run_id: str
    request: RunRequest
    model_a_summary: ModelRunSummary
    model_b_summary: ModelRunSummary
    agreement_rate: float
    # Issues excluded from agreement_rate's numerator/denominator because at least
    # one model failed to produce a prediction — see metrics.agreement_rate.
    # Defaults to 0 so older persisted run files (from before this field existed)
    # still load fine.
    agreement_excluded_count: int = 0
    per_issue: list[dict]  # merged per-issue rows for the UI (see storage.py for shape)
