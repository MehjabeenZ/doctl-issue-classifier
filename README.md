# doctl issue-classification eval harness

An evaluation harness that classifies GitHub issues from `digitalocean/doctl`
into one of 6 labels using DigitalOcean Serverless Inference (SI) models,
compares candidates side by side on accuracy/cost/latency/throughput, and
turns that into a production recommendation — not a one-off benchmark of this
one repo, but a proving ground for a customer's broader "high volume, many
repos, suspect we're overpaying a frontier model" workload.

**Running application:** https://doctl-issue-classifier.onrender.com/
(deployed on Render's free tier — the first request after a period of
inactivity may take 30–60s to wake the instance up).

**This hosted instance is protected by HTTP Basic Auth**, deliberately *not*
documented here — a public URL with an unauthenticated endpoint sitting in
front of a real, billed SI API key shouldn't be reachable by anyone who
happens to find the link, and a shared credential doesn't belong in a
committed file either. Once authenticated, the app is the real, fully live
thing: pick any two models, set concurrency/limit, and run a genuine
comparison against the live corpus, same as running it locally. It also
loads the real, already-persisted `mistral-3-14B` vs `deepseek-4-flash`
full-corpus result on startup, so there's something to inspect immediately
without waiting on a fresh run. Ask for access if you'd like to use it live.

**The Docker path below is the primary way to reproduce a genuinely live
run**, not a fallback — bring your own `SI_API_KEY` (see "Run it yourself")
and there's no credential exchange needed at all: no auth wall applies
locally/in Docker by default, it's your own key and your own container.

## The scenario

A customer runs issue classification at high volume against a frontier model,
across many repos and product lines, and suspects they're overpaying. `doctl`
(DigitalOcean's own CLI, ~536 GitHub issues) is the proving ground: a real,
messy, inconsistently-labeled corpus used to build and validate an evaluation
methodology the customer could point at the rest of their workload.

## Ground truth: how it was built

doctl's own maintainer labels are exactly as inconsistent as the exercise
warns: applied by different people over years, using label names (`suggestion`
vs `enhancement`, `docs`, `security vulnerability`) that don't map 1:1 onto the
customer's 6-class schema (`bug`, `enhancement`, `question`, `documentation`,
`security`, `other`).

**Step 1 — rule-based mapping.** doctl's real labels were mapped onto the
6-class schema wherever exactly one category signal was present:

| doctl label | → schema class |
|---|---|
| `bug` | `bug` |
| `security vulnerability` | `security` |
| `question` | `question` |
| `docs` | `documentation` |
| `suggestion`, `enhancement`, `api-parity` | `enhancement` |

Meta/process labels (`windows`, `packaging`, `snap`, `hacktoberfest`, `good
first issue`, `help wanted`, `waiting-response`, `do-api`, `wip`, `blocked`, …)
carry no category signal on their own and were ignored. This gave a clean,
unambiguous mapping for **301 of 536 issues (56%)**.

**Step 2 — validate the rule, don't just trust it.** A stratified random
sample of 40 of those 301 issues was pulled, with every label stripped, and
independently re-read blind by two separate labelers with no access to
doctl's real labels or to each other's answers. Result: **100% agreement**
(30/40 unanimous across rule-label + both blind reads, 10/40 resolved
2-of-3, zero total mismatches). That's evidence the rule-mapped tier is
trustworthy, not an assumption.

**Step 3 — the hard tier.** The remaining 235 issues (no maintainer label at
all, a label that carries no category signal, or conflicting category labels)
were blind double-labeled by the same two independent labelers: **92% raw
agreement** (217/235). The 18 disagreements were read and adjudicated
directly.

**The split that matters — scored vs. unscored.** The 301 rule-mapped-and-
validated issues became the app's **official ground truth**
(`data/processed/ground_truth.json`) — their provenance traces to real doctl
maintainer triage, independently verified. The other 235 issues were labeled
by AI (the two blind labelers), which is methodologically different from
human-derived ground truth — scoring model accuracy against them would be
evaluating one AI system against another AI system's opinion, not against a
real answer key. So they're kept separate
(`data/processed/silver_labels_unscored.json`, never fed into scoring) and
populate the app's **unscored view** with no label revealed — which also
happens to be the honest framing: this is the ambiguous backlog doctl's own
maintainers never cleanly triaged, exactly the kind of thing a customer would
want classified without a pre-existing answer key.

**A gap worth stating plainly, not hiding:** the scored set has **zero
examples of `documentation` or `other`** — doctl maintainers essentially
never used those categories cleanly enough to survive the rule mapping.
Per-class precision/recall/F1 for those two report "no data" rather than a
misleading 0% (see `support_by_class` in `backend/app/metrics.py`). This is a
real limitation of doctl specifically as a proving ground, worth naming when
this methodology is pointed at the customer's other repos — some of those
will have enough documentation/other examples to score properly, doctl just
doesn't.

Reproduce this: `scripts/ingest_issues.py` → `scripts/build_ground_truth_tiers.py`
→ (blind labeling step) → `scripts/reconcile_ground_truth.py`.

## Model selection

**Scope filter.** DO's `/v1/models` serves 72 models total, including
closed/proprietary ones (Anthropic Claude, OpenAI's proprietary line) that are
out of scope here. After filtering to open-weight, task-fit (chat/instruction,
not embeddings/image/etc.), and excluding `router:*` meta-models (they pick an
underlying model per call, which breaks per-call cost traceability), a
license-research pass narrowed the field further — one ambiguous case
(`qwen3.8-max`, unclear which license DO actually serves under that id) and one
with no public price (`minimax-m2.5`) were excluded rather than gambled on.

**Selection criteria** — beyond the obvious (license, task fit, cost, latency,
parse-error rate), the shortlist was built against a fuller set once a first
pass was challenged as incomplete: org/architecture/size diversity, reasoning
vs. non-reasoning coverage, **self-consistency** (temperature=0 is not a
determinism guarantee — MoE routing and batching introduce real variance),
**native structured-output support** (as a criterion distinct from the
parse-error rate it produces downstream), **throughput ceiling** (separate
from per-call latency — the binding constraint at volume is often the rate
limit, not how fast one call returns), **release/deprecation risk** (a dated
snapshot id gets superseded faster than an undated "current" line), and
**data governance** (stated explicitly even though it doesn't differentiate
here — same DO infrastructure regardless of which open-weight model is used).

**Six-model screening shortlist**, chosen to span these axes:

| Model | Org | Arch | Reasoning? |
|---|---|---|---|
| `openai-gpt-oss-20b` | OpenAI (open-weight) | ~21B MoE | Yes, adjustable |
| `openai-gpt-oss-120b` | OpenAI (open-weight) | ~117B MoE | Yes, adjustable |
| `mistral-3-14B` | Mistral | 14B dense | No |
| `llama-4-maverick` | Meta | 400B MoE | No |
| `deepseek-4-flash` | DeepSeek | 284B MoE | Yes, dual-mode |
| `glm-5.3-flash` | Z.ai | 320B MoE | Likely yes |

**Real screening results** (301 scored issues × 6 models, 1,806 live calls
against the real SI API, ≈$0.18 total):

| Model | Accuracy | Cost/correct classification | p50 / p95 latency | Errors |
|---|---|---|---|---|
| **mistral-3-14B** | **85.7%** | $0.000136 | **460ms / 676ms** | none |
| deepseek-4-flash | 85.0% | **$0.0000455** | 3891ms / 7809ms | none |
| openai-gpt-oss-20b | 83.1% | $0.000101 | 1185ms / 3824ms | none |
| glm-5.3-flash | 80.7%* | $0.000225* | 1614ms / 8574ms | 4/301 parse errors* |
| openai-gpt-oss-120b | 81.4% | $0.0000812 | 2523ms / 5873ms | none |
| llama-4-maverick | 78.4% | $0.000138 | 1485ms / 2344ms | none |

*glm-5.3-flash's parse errors were `finish_reason=length` — the model spent
its full token budget on chain-of-thought before emitting an answer. Doubling
the output-token budget cut errors from 12/301 to 4/301, but notably the 4
that still failed were almost entirely *different issues* than the original
12 on a re-run at temperature=0 — real evidence that this model's reasoning
length is not deterministic call-to-call, not just a budget-tuning problem.

**Final selection: `mistral-3-14B` (production default) + `deepseek-4-flash`
(alternative for lower-volume workloads).** Both were then run through two
further checks:

- **Self-consistency** (same issue, 3 repeats, temperature=0): both models are
  highly stable — 97% unanimous, 100% majority. No differentiator.
- **Observed throughput at tested concurrency** (ramped concurrency up to 32,
  real rate-limit behavior, 40 calls/level): `mistral-3-14B` handled every
  level with zero errors — its actual ceiling wasn't found, only that it's
  above 30 req/s; `deepseek-4-flash` topped out around **3.6 req/s** and was
  already rate-limiting by concurrency 8. This is a small per-level sample and
  an isolated single-model probe (the app runs both models concurrently), so
  treat these as directional, not exact production limits — but the ~8-10x
  gap between them is large enough that it isn't sample noise.

This is the finding that actually decides the recommendation. Judged purely
on cost-per-token, `deepseek-4-flash` looks like the better deal — it's about
3x cheaper per correct classification. But that number only matters if you
can push volume through the model, and for "high volume across many repos,"
deepseek's observed throughput ceiling is roughly an order of magnitude below
mistral's. **`mistral-3-14B` is the production recommendation** — accuracy
between the two is close enough on this sample (301 scored issues; a paired
comparison on the full-corpus run finds `mistral-3-14B` correct-only on 16
issues vs. `deepseek-4-flash` correct-only on 12 — McNemar's test on those 28
discordant pairs gives χ²=0.32, p=0.57, nowhere near significant) that it isn't
what decides this. Latency and, especially, throughput are what do: `mistral-3-14B`
is faster per call and sustains far higher load, and its cost-per-call, while
higher than deepseek's, is still a small fraction of a frontier model's.
`deepseek-4-flash` remains worth reconsidering specifically for a lower-volume workload (a
smaller repo, or genuinely infrequent classification) where the throughput
ceiling never binds and its lower per-token price would matter more than it
does here. `deepseek-4-flash` pricing ($0.07/M input, $0.17/M output) was
confirmed directly against the DO billing dashboard, not just the catalog
research pass.

A side finding worth naming: `llama-4-maverick` (400B, ~28x more parameters
than `mistral-3-14B`) scored *worse* (78.4% vs 85.7%) and 3x slower — bigger
did not mean better for this task, which is itself a useful data point for a
customer inclined to assume scale is the answer.

## Evaluation methodology

- **Per-issue inference, no batching.** Each issue is its own request — the
  exercise requires per-call cost/latency/retry granularity, and batching
  would destroy that.
- **Configurable concurrency**, no rebuild required — `DEFAULT_CONCURRENCY`
  env var, overridable per-run from the UI.
- **Retries**: exponential backoff (`tenacity`), retried on 429/5xx/timeout,
  not retried on other 4xx (a malformed request stays malformed on retry).
  Each result records the error type it ultimately succeeded or failed with
  (`rate_limit` / `timeout` / `parse_error` / `other`), so the UI can break
  down errors by cause instead of a single opaque failure count. `parse_error`
  is tracked separately from `other` because it's a materially different
  failure mode — "the model won't follow the output format" has a different
  fix than "the request itself failed."
- **Structured output with fallback**: every call first tries the SI API's
  `response_format` (a strict JSON schema over the 6 labels); if a model 400s
  on that, the harness remembers it for the rest of the run and falls back to
  prompt-only + regex/bare-word parsing, rather than paying the discovery cost
  on every one of 500+ calls per model.
- **Prompt design**: no few-shot examples (the more useful number for a
  customer is "what does this model do zero-shot," not what prompt
  engineering can squeeze out of it), `temperature=0`.
- **Metrics**: accuracy, per-class precision/recall/F1 with explicit `None`
  for zero-support classes (never a misleading 0%), confusion matrices
  (shaded by ground-truth support, so a class with failed calls can't render
  as if every prediction landed), p50/p95 latency paired with the concurrency
  they were measured at, wall-clock, throughput (req/s), and **full-run cost
  per correct classification** as the headline economic number — raw
  cost-per-call ignores accuracy, raw accuracy ignores cost, this composite
  gets closer to the customer's actual question than either alone. One
  caveat stated plainly: as computed, the numerator is cost across the full
  corpus while the denominator is correct count on the scored subset — a
  defensible workload-level proxy, not literally cost-per-call for one
  matched population. See the table below and `OperationalMetrics.jsx`.

## Cost, latency, throughput

The app's Operational view computes and displays all of the above live for
any comparison run. Below is the real result of running the actual
recommended pair (`mistral-3-14B` vs `deepseek-4-flash`) against the **full
536-issue corpus** through the app itself (not the standalone screening
script), at the app's default concurrency of 8 — this is what "run it
yourself" reproduces:

| | `mistral-3-14B` | `deepseek-4-flash` |
|---|---|---|
| Accuracy (301 scored) | 84.7% | 83.4% |
| Total cost (536 calls) | $0.0567 | $0.0193 |
| Full-run cost / correct* | $0.000222 | $0.0000767 |
| p50 / p95 latency | 416ms / 903ms | 2641ms / 6588ms |
| Wall-clock (both models run concurrently) | 62.5s | 213.3s |
| Throughput | 8.6 req/s | 2.5 req/s |
| Errors (out of 536) | 3 rate-limited | 4 rate-limited |

*total cost across all 536 calls ÷ correct count on the 301 scored issues —
see the caveat above.

Agreement rate between the two models across the full corpus: **89.8%**
(475/529 comparable issues; 7 of 536 excluded because at least one model
failed to produce a prediction on that issue — see `metrics.agreement_rate`).

**Honest note on the accuracy numbers**: both are ~1 point lower here than in
the 301-issue screening pass used for model selection (85.7%/85.0%). Two real,
identified causes, not measurement noise glossed over: (1) neither model is
perfectly deterministic at `temperature=0` — a separate self-consistency check
found ~97% (not 100%) unanimous labels across repeated identical calls, so a
small amount of run-to-run drift is expected and real; (2) a handful of calls
in this run were rate-limited past their retry budget (3 for mistral, 4 for
deepseek, out of 536 each) and count as misses in the accuracy calculation
rather than being silently excluded. Both effects are small, expected, and
consistent with what the self-consistency and rate-limit probes predicted
ahead of this run — not a discrepancy that changes the recommendation.

## Production handling: from doctl to the rest of the workload

This proves out a recommendation on one repository. Getting from here to the
customer's full workload (many repos, many product lines) is a separate set
of questions.

**Rollout shape.** Don't cut over all repos at once. Start with a shadow run:
classify the same tickets with both the incumbent frontier model and the
recommended SI model(s) for a period, compare agreement and where they
diverge, without acting on the SI model's output yet. Move to production
traffic repo-by-repo (or product-line-by-product-line) once shadow agreement
and per-class accuracy on that repo's own historical labels clear a bar the
customer sets — not a global bar, since label conventions and issue-mix vary
by repo the same way they did within doctl's own history.

**What has to be true before each step:**
- *Before shadow mode*: a ground-truth sample for that repo, built the same
  validated way as here — you cannot know if a model is ready for a repo you
  have no answer key for.
- *Before cutover*: a fallback path exists and is tested, not theoretical
  (below), and someone owns watching the error-rate and disagreement-rate
  dashboards, not just the accuracy number.
- *Before scaling concurrency up*: real rate-limit behavior from the provider
  is known per model, not assumed — this exercise's own screening run found
  an 8x difference in throughput ceiling between two models with near-identical
  accuracy, so this isn't a hypothetical risk.

**Where the chosen models fall short.** Two known failure shapes, generalized
from what doctl's own data exposed:
1. **Structurally rare classes** (doctl's `documentation`/`other`) — a class
   with too little signal to validate against will silently ship
   un-validated. Fix: track per-class support at rollout time, not just
   aggregate accuracy, and flag any repo/product line where a class's support
   is too thin to trust.
2. **Parse failures and low-confidence outputs** — route to a fallback model
   (a larger/more capable SI model, or in the worst case back to the frontier
   model) rather than accepting a guess. The per-issue, non-batched design in
   this harness exists specifically so individual cases can be retried or
   routed without touching the rest of the run. Not implemented here —
   designed, not built, since the exercise asks only that the path be thought
   through.

**What this does not solve** (explicitly out of scope, called out rather than
glossed over): drift in issue phrasing/labeling conventions over time,
multi-label issues (this schema forces exactly one label, same constraint the
customer's schema has), and repos with too few historical issues to build a
trustworthy ground truth sample at all — those need either borrowed labels
from a similar repo or a larger human-labeling investment before automation
is trustworthy there.

## What was deliberately not built

Stated together since the exercise explicitly grades this list:

- No per-user authentication/authorization model. The hosted deployment sits
  behind a single shared HTTP Basic Auth credential (env-var gated, off by
  default) specifically to stop anonymous public spend against a real SI key
  — that's access control, not a real accounts/roles system. Before real
  multi-user exposure, actual accounts and permissions would be required.
- No real datastore — flat JSON files, single-writer, no concurrent-run
  support. The first thing to fix before scaling past one engineer / one
  repo at a time.
- No live per-issue progress streaming during a run — binary running/done
  status via polling only.
- No fallback-model routing implemented (designed, not built — above).
- No multi-label classification — one label per issue, matching the
  customer's own stated schema, not a limitation introduced here.
- No ingestion of issue comments/discussion threads — title + body only, to
  stay within the exercise's "thin ingestion" guidance.
- No CI pipeline, no linter config beyond a `pyrightconfig.json` for editor
  sanity.
- No hardening of GitHub API pagination beyond a basic rate-limit-aware sleep
  — sufficient for a one-time ~536-issue pull, not a continuously-syncing
  pipeline across many repos.

## Architecture

```
backend/app/        FastAPI eval harness (async, per-issue inference, retries, metrics)
frontend/            React UI: Scored / Unscored / Operational views
data/raw/            frozen GitHub issue snapshot (stable across runs)
data/processed/      ground_truth.json (scored, 301), silver_labels_unscored.json (dev-only, 235)
data/runs/           persisted eval run results (per run_id) — run_1789106490.json is the
                     real, committed full-corpus result this README's numbers come from
scripts/             ingestion, ground-truth construction, model screening/consistency/rate-limit probes
Dockerfile           multi-stage: builds frontend, serves it + the API from one container
```

## Run it yourself

Works today with no API key, in dry-run mode (synthetic responses so the full
harness — retries, metrics, UI — is exercisable without spending credits):

```bash
docker build -t doctl-eval .
docker run -p 8080:8080 -e DRY_RUN=true doctl-eval
# open http://localhost:8080
```

For a real run with an SI API key:

```bash
docker run -p 8080:8080 \
  -e SI_API_KEY=<your key> \
  -e SI_BASE_URL=https://inference.do-ai.run/v1 \
  -e DEFAULT_CONCURRENCY=8 \
  doctl-eval
```

The UI defaults to comparing `mistral-3-14B` vs `deepseek-4-flash` — the
recommended pair — but any two models from the live catalog can be selected.

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SI_API_KEY` | _(none)_ | DigitalOcean Serverless Inference API key. Required unless `DRY_RUN=true`. |
| `SI_BASE_URL` | `https://inference.do-ai.run/v1` | OpenAI-compatible SI base URL. |
| `DEFAULT_CONCURRENCY` | `8` | Default parallel in-flight requests; overridable per-run in the UI. |
| `MAX_OUTPUT_TOKENS` | `1024` | Per-call output token budget — sized generously so reasoning models' chain-of-thought isn't truncated before the final label. |
| `DRY_RUN` | `false` | If `true`, skips real API calls and returns synthetic (noisy, not perfect) responses. |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | _(none)_ | If both are set, the whole app requires HTTP Basic Auth with these credentials. Used on the hosted Render deployment only — leave unset for local/Docker use. |
| `MAX_RETRIES` | `3` | Per-request retry attempts on rate limit/timeout/5xx. |
| `DATA_DIR` | `data` | Where the corpus, ground truth, and run results live. |

### Local dev (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
DRY_RUN=true uvicorn app.main:app --app-dir backend --reload &

cd frontend && npm install && npm run dev
# frontend dev server proxies /api to localhost:8000
```

---

Every decision above has more depth behind it than fits here on purpose —
alternatives considered and rejected, exact numbers behind every claim, and a
running log of bugs found and fixed during real-API testing — kept as a
personal working document rather than included in this deliverable, since
the exercise asks this README to carry the reasoning and conclusions, not a
full decision log. Happy to go deeper on any specific tradeoff in the review
session.
