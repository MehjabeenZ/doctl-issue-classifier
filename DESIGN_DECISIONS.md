# Design decisions & tradeoffs — full rationale log

This is the prep document, not the deliverable README. The README says what was
built and what it showed; this says **why every choice was made, what else was
considered, and what was deliberately not done** — organized so it can be read
straight through before the review session. Where something is still a guess
(pending real SI credits), it's marked `GUESS` rather than dressed up as a
decision backed by evidence.

---

## 1. Tech stack & architecture

**Backend: Python + FastAPI**, not Node/Express, Go, or Django.
- Why: the core hard requirement is concurrent async I/O (hundreds of in-flight
  HTTP calls to an inference API) with per-call bookkeeping (tokens, cost,
  latency, error type) — Python's `asyncio` + `httpx` handles this natively, and
  `pydantic` gives free request/response validation that matches the
  OpenAI-compatible JSON shape the SI API uses.
- Considered: Go would give better raw concurrency headroom and a smaller
  container, but at ~500-1000 total requests per run, Python's asyncio ceiling
  is nowhere close to being the bottleneck — the bottleneck is the inference
  API's own rate limits, not the client. Go would have been over-engineering for
  the actual constraint.
- Considered: Django — much heavier than needed for an API with no auth, no ORM
  models beyond flat JSON, no admin panel use case.

**Frontend: React + Vite**, not server-rendered HTML/htmx, not vanilla JS.
- Why: the UI has real interactive state — two tabs with independent filters, a
  job-polling loop, expandable rows, a disagreement toggle — that's naturally a
  component tree with local state, and Vite gives a fast dev loop for iterating
  on chart components.
- Considered: htmx/server-rendered — would avoid a Node build stage in Docker
  entirely (smaller, simpler image) and is arguably the more "boring, robust"
  choice for an app this size. Went with React anyway because the UI has enough
  cross-cutting state (job status driving three different views, a shared
  corpus stat) that it's more naturally expressed with client-side state than
  with server-rendered partial swaps, and because a polished multi-view
  comparison UI is closer to what "recommendation you'd deliver to a customer"
  implies than a plainer server-rendered page.

**Storage: flat JSON files**, not SQLite, not Postgres.
- Why: the corpus is ~536 issues, single-writer, no concurrent multi-user
  access, and the deliverable literally asks for "your labeled dataset and any
  persisted eval results" as files — JSON files under `data/` directly are that
  deliverable, no export step needed.
- Considered: SQLite — would give query flexibility (e.g., "show me all issues
  where models disagreed across the last 5 runs") that flat files don't. Not
  worth the added complexity for a tool that runs one comparison at a time and
  loads the whole corpus into memory every time regardless.
- **Production caveat, explicitly**: flat files do NOT survive the jump to the
  customer's real workload (many repos, many product lines, presumably
  multiple engineers running comparisons concurrently). That's a real
  datastore's job. Called out again in §5.

**Single Docker container** (multi-stage: Node stage builds the frontend,
Python-slim stage serves both the API and the static build via FastAPI's
`StaticFiles`), not docker-compose with separate frontend/backend containers.
- Why: the deliverable literally asks for "a Dockerfile that builds a runnable
  container" (singular), and a reviewer running this should not need to
  orchestrate multiple services to see it work.
- Considered: separate containers — more realistic for how you'd actually scale
  this in production (independent redeploys, independent scaling of the API vs.
  static asset serving), but that's unwarranted complexity for a single-engineer
  demo tool. Named explicitly as a "what I chose not to do."

---

## 2. Ground truth dataset — the highest-scrutiny decision

**The core problem, confirmed by the data, not just the exercise's warning**:
doctl's real GitHub labels don't map cleanly onto the 6-class schema. Pulling
the label list and cross-tabulating against issue content showed:
- `suggestion` (89 uses) is the real "feature request" label; the literal
  `enhancement` label (16 uses) is used far less — same concept, inconsistent
  labeling habit across years of maintainers.
- No `security` label exists; `security vulnerability` (26 uses, all
  WhiteSource-bot-filed CVE alerts) is the closest fit.
- `docs` was used only 3 times, total, in the entire repo's history, and all 3
  times alongside a conflicting second label (e.g. `bug`+`docs`) — meaning zero
  issues have `docs` as an unambiguous single signal.
- 195 of 536 issues (36%) have no labels at all.

**Options considered for constructing ground truth:**

| Option | Why not chosen (or chosen) |
|---|---|
| Trust all maintainer labels wholesale | Rejected — the data itself proves this is unreliable (documentation label alone shows why). |
| Hand-label a small random sample (e.g. 100 issues), ignore maintainer labels entirely | Considered, but a 100-issue random sample would contain only ~5 `security` examples (26/536 ≈ 4.9%) and effectively zero clean `documentation`/`other` examples — too thin to trust per-class metrics on the classes that most need scrutiny. Also throws away a free, much larger signal (the 301 rule-mappable issues) for no real gain in rigor. |
| Use AI (Claude) to label the entire corpus, treat it all as ground truth | Rejected — this was my own initial mistake mid-build (see below), corrected once I noticed it contradicts the "ground truth must be independent of the systems under test" principle: scoring one AI's predictions against another AI's opinion isn't ground truth, it's agreement between two AI systems. |
| **Chosen: tiered rule-mapping + independent blind validation + human-adjudicated hard tier** | Described below. |

**What was actually built, in order:**

1. **Rule-based mapping** of doctl's real labels onto the 6-class schema
   (`bug`→bug, `security vulnerability`→security, `question`→question,
   `docs`→documentation, `suggestion`/`enhancement`/`api-parity`→enhancement),
   applied only where exactly one category signal existed. Gave 301/536 (56%)
   clean-mapped issues, for free, at zero labeling cost.
2. **Validation, not blind trust**: a stratified sample of 40 of those 301 (all
   labels stripped) was independently re-read blind by two separate labeling
   agents with no access to doctl's real labels or to each other's answers.
   Result: 100% agreement (30/40 unanimous across rule + both blind reads,
   10/40 resolved 2-of-3, zero total mismatches) — this is the evidence the
   rule mapping is trustworthy, not an assumption.
3. **The hard tier** (235 issues: unlabeled, meta-label-only, or
   conflicting-labels) was blind double-labeled by the same two independent
   agents: 92% raw agreement. The 18 disagreements were read and adjudicated
   directly (by me, reading title + body against the schema's own definitions).
4. **The critical split**: only the 301 rule-mapped-and-validated issues became
   the app's official `ground_truth.json`, used for scoring. The 235
   AI-labeled issues went into a separate `silver_labels_unscored.json`,
   **never fed into scoring**, and populate the app's unscored view with no
   label revealed. This also happens to be the honest framing: those 235 are
   exactly the ambiguous backlog doctl's own maintainers never triaged, which
   is what an unscored view is supposed to represent.

**Why subagent double-labeling instead of the two of us hand-labeling 275
issues personally**: the exercise explicitly says "we do not expect you to
hand-label every issue... what matters is you can articulate the reasoning."
Two independent labelers plus a human adjudication pass on disagreements is a
standard pattern in real annotation pipelines (double-annotation + adjudication
for inter-rater reliability) — this substitutes AI annotators for the
redundant first-pass labor while keeping a human in the loop specifically for
the disagreements, which is where judgment actually matters.

**The honest limitation I'd volunteer before being asked**: the two "independent"
blind labelers were both Claude-based agents — independent in context and
access (no shared state, no visibility into each other), but not independent in
underlying model family. So the 92% and 100% agreement numbers measure
consistency within one model family's judgment, not true inter-annotator
reliability across genuinely diverse human annotators. This is why the
rule-mapped tier (whose ground truth traces to real human maintainer decisions,
not AI judgment) is the *only* tier used for scoring — it bounds the risk: even
if the AI labelers share a blind spot, the 100%-agreement validation check
against that independent, human-sourced signal is real evidence, not
AI-checking-AI.

**Known gap, stated plainly**: the scored set has **zero examples of
`documentation` or `other`**. This isn't a bug in the methodology — doctl's own
maintainers essentially never used those categories cleanly enough to survive
the rule mapping. It means this app's confusion matrix rows and per-class F1
for those two classes show "no data" rather than a number, and it means doctl
specifically is a weak proving ground for those two classes even though the
overall methodology (rule-map → validate → adjudicate hard tier) would work
fine on a repository where those classes are better represented.

---

## 3. Model selection

**Status as of 2026-09-09**: real SI credits and a working model access key exist.
The live catalog (72 models) has been pulled and license-researched, a 6-model
screening shortlist is built and the harness is ready to run it, but **the actual
screening run has not happened yet** — a first attempt hit a real bug (below) and
was paused at the user's request before any full run completed, pending an
explicit go-ahead. Everything in this section is the *process and shortlist*,
not yet real accuracy/cost/latency results.

### Scope filter: what's even eligible

DO's `/v1/models` returns 72 models, but that includes closed/proprietary models
served through the same endpoint (Anthropic Claude, OpenAI's proprietary
GPT-5.x/o-series) which the exercise puts explicitly out of scope. A license
research pass (WebSearch against each candidate's model card/HF repo/release
announcement, 2026-09-09) also surfaced one genuinely ambiguous case:
**`qwen3.8-max`** — Alibaba shipped it as a closed, paid API first, then later
open-weighted the underlying checkpoint under a separate custom license. It's not
confirmed which one DO is actually serving under that model id, so it's excluded
rather than gambled on; `qwen3.5-397b-a17b` (confirmed Apache 2.0) covers the same
size class cleanly. `minimax-m2.5` is open-weight per the research but doesn't
appear on DO's public pricing page at all, so there's no honest cost number for
it — also excluded. Also excluded: embeddings/rerankers, image/video/audio-gen
models, and DO's `router:*` meta-models (these silently pick an underlying model
per call, which breaks the "traceable cost per call" requirement — you wouldn't
know which model actually produced a given classification).

### Original criteria (used to build the first shortlist)

1. Confirmed open-weight license (not just "technically callable with this key")
2. Task fit (text/chat instruction-following, not embeddings/image/etc.)
3. Org/architecture/size diversity across the shortlist
4. Reasoning vs. non-reasoning coverage
5. Per-token cost
6. Latency (p50/p95)
7. Parse/format-compliance error rate

**The user pushed on whether this was actually the best available criteria set**
— a fair challenge, and the honest answer was no, not fully. A research pass
(WebSearch, 2026-09-09) against current production-LLM-selection practice
surfaced real gaps:

### Criteria added after that research pass

8. **Determinism / self-consistency.** Temperature=0 is not a determinism
   guarantee — MoE routing, batching, and kernel non-associativity all introduce
   variance, and current literature explicitly measures "self-consistency rate"
   under repetition as its own axis, flagging smaller/quantized models as
   typically less stable. For a 6-way label with real downstream consequences,
   a model flip-flopping on identical input is a correctness bug, not a style
   footnote. Built (not yet run): `scripts/check_self_consistency.py` — samples
   30 issues, calls each 3x per model, reports unanimous/majority agreement rate.
9. **Native structured-output support**, as a criterion distinct from the
   parse-error rate it produces downstream. Prompt-only JSON extraction is
   reported to fail 8-20% of the time at production scale; schema-constrained
   decoding removes that failure mode at the source. Implemented in
   `inference_client.py`: every call now tries `response_format` (a strict JSON
   schema enforcing the 6-label enum) first, and falls back to prompt-only +
   the regex/bare-word parser on a 400, remembering per-model for the rest of
   the run so the discovery cost isn't paid on every one of 500+ calls. Not
   every backend behind DO's unified API is guaranteed to honor this — the
   fallback exists specifically because that's expected to vary by model.
10. **Throughput ceiling, separate from per-call latency.** Smaller/cheaper
    models commonly get much higher RPM/TPM ceilings than flagship models on the
    same provider — for "high volume across many repos," the binding constraint
    at scale is often the rate limit, not p50 latency. These are two different
    numbers; the harness was only reporting one. Built (not yet run):
    `scripts/probe_rate_limits.py` — ramps concurrency for one model at a time
    and finds where rate-limiting kicks in. Deliberately scoped to one model per
    invocation, run against whichever model(s) survive the accuracy/cost screen,
    not blanket-applied to all 6 up front (it's a load test, not a cheap check).
11. **Release/deprecation risk**, distinct from license legality. A dated
    point-in-time snapshot (id suffix like `-0731`) tends to get superseded and
    pulled faster than a vendor's undated "current" line. Added a `release_risk`
    field to `ModelPricing` in `model_catalog.py`. This immediately changed a
    real decision, not just a documentation note: the shortlist originally had
    `deepseek-v4-flash-0731` (a dated snapshot); swapped to the undated
    line, which turned out to also be *cheaper* ($0.068/$0.168 per 1M vs
    $0.080/$0.252) — a case where a criterion added for risk-management reasons
    also happened to strictly dominate on cost, not a tradeoff at all.
    **Correction, 2026-09-10**: the undated id was recorded as `deepseek-v4-flash`,
    which doesn't exist — a smoke test 404'd on it and the real live id is
    `deepseek-4-flash` (no "v"). Fixed in `model_catalog.py`. **Pricing confirmed
    the same day directly from the DO dashboard** (Gradient AI Platform > Models):
    $0.07/$0.17 per 1M input/output tokens — close to the original $0.068/$0.168
    placeholder (off only in rounding, from the same WebFetch pass flagged
    elsewhere in this doc as unreliable). Worth noting for the review session:
    the earlier-flagged-as-possibly-hallucinated research got the *number* right
    here even though it had the *id* wrong — a reminder that "looked plausible
    and was numerically close" isn't the same as "verified," which is exactly
    why it got checked against the dashboard rather than trusted on that basis.
12. **Data governance/compliance** — a standard line item in every practitioner
    framework the research found. Doesn't differentiate much between candidates
    here (same DO infrastructure, same data-handling terms regardless of which
    open-weight model processes the request), but worth stating rather than
    omitting: no issue content leaves DO's infrastructure boundary any
    differently depending on which of these 6 models is selected.

**One finding that reframes the reasoning-vs-non-reasoning axis itself**: the
research reports that reasoning/chain-of-thought models tend to add cost,
latency, and output variance *without* reliable accuracy gains specifically on
simple, fixed-schema classification tasks (as opposed to open-ended reasoning
tasks) — the opposite of assuming "reasoning = better." The exercise names
reasoning-vs-non-reasoning as "a good direction" for the final tradeoff, but
whether reasoning actually helps *this specific task shape* is being treated as
something the screening run needs to answer empirically, not something assumed
going in either direction.

### A real bug this surfaced

Increasing `max_output_tokens` (600, later 1024) to stop truncating reasoning
models' chain-of-thought before their final answer wasn't sufficient by itself —
the first real-API run crashed with `AttributeError: 'NoneType' object has no
attribute 'strip'` because some responses came back with `content: null`
entirely (the reasoning consumed the full token budget before ever emitting an
answer, or the API splits chain-of-thought into a separate field and leaves
`content` empty). Fixed in `inference_client.py`: content is coerced to `""` if
null, and if that empty content coincides with `finish_reason == "length"`, the
resulting `parse_error`'s message says so explicitly (truncated-by-budget) rather
than looking like a generic formatting failure — those have different fixes
(raise `max_output_tokens` further vs. the model just isn't following
instructions) and conflating them would point a customer at the wrong remedy.

### The 6-model screening shortlist (see `model_catalog.py` for full detail)

| Model | Org | Arch | Reasoning? | Role |
|---|---|---|---|---|
| `openai-gpt-oss-20b` | OpenAI (open-weight) | ~21B MoE | Yes, adjustable | Small/cheap end |
| `openai-gpt-oss-120b` | OpenAI (open-weight) | ~117B MoE | Yes, adjustable | Same family — isolates size effect |
| `mistral-3-14B` | Mistral | 14B dense | No | Small dense, non-reasoning baseline |
| `llama-4-maverick` | Meta | 400B MoE | No | Large, non-reasoning, well-known reference |
| `deepseek-4-flash` | DeepSeek | 284B MoE | Yes, dual-mode | Cost-efficient large-MoE (swapped from the dated `-0731` snapshot — see criterion 11; id corrected 2026-09-10 after a smoke-test 404, pricing confirmed against DO dashboard the same day) |
| `glm-5.3-flash` | Z.ai | 320B MoE | Likely yes | Different org, efficient large-MoE |

Set aside for the screening pass specifically (cost/redundancy with a cheaper
same-capability-class model already above, not eliminated from consideration
outright): `deepseek-3.2`, `deepseek-v4-pro`/`-0813`, `qwen3.5-397b-a17b`,
`glm-5.2`/`glm-5.3` (full), `kimi-k2.6`/`k3`, the Nemotron family,
`gemma-4-31B-it`, `mimo-v2.5-pro`, `arcee-trinity-large-thinking`.

### Screening run process — a worked example of "confirm before spend," 2026-09-10

Before spending any real SI credits on the full 301-issue × 6-model screening
pass (1,806 calls), a staged rollout was used rather than a single all-or-nothing
run. This is worth recounting in the review session as the actual production
discipline being argued for elsewhere in this doc (§6), demonstrated on the
harness itself:

1. **Code changes made first, before any spend**: `scripts/run_model_screening.py`
   gained `--limit N` (run only the first N scored issues), `--model MODEL_ID`
   (repeatable, run a single model in isolation), per-model **incremental
   persistence** (results write to disk after each model finishes, not only
   after all 6 — so a crash mid-run doesn't lose already-paid-for results and a
   retry doesn't need to re-spend on models that already succeeded), and
   inline console logging of each `error_message` (previously only aggregated
   error *counts* were kept, which turned out to hide the actual cause of a
   failure — see below).
2. **`--limit 1 --model openai-gpt-oss-20b`** (1 real call) — confirmed the
   client, pricing calc, and structured-output path work end to end before
   spending anything more.
3. **`--limit 5`** across all 6 models (30 calls, ~$0.002 total) — surfaced a
   real bug immediately: **`deepseek-v4-flash` 404'd on every call.** The model
   ID recorded in `model_catalog.py` doesn't exist on the live `/v1/models`
   endpoint at all; the real id is `deepseek-4-flash` (no "v"). This id (and its
   attached pricing, $0.068/$0.168 per 1M tokens) traced back to the earlier
   WebFetch-based catalog research already flagged elsewhere in this doc as
   partly hallucinated — the smoke test is what actually caught it, not manual
   review. Fixed the id in `model_catalog.py` and explicitly annotated the
   pricing there as unverified (no re-confirmation against DO's real billing
   dashboard yet), rather than quietly trusting a number that had just been
   shown to be attached to a nonexistent model. **Later confirmed directly
   from the DO dashboard** (see the "Final selection" section below): real
   price is $0.07/$0.17 per 1M tokens, close to the $0.068/$0.168 placeholder.
4. Re-ran `--limit 5 --model deepseek-4-flash` with the corrected id — clean,
   80% accuracy on n=5, zero errors — before trusting it in the full run.
5. **Full run**: `python3 scripts/run_model_screening.py` (301 scored issues ×
   6 models, 1,806 real calls). Total cost **≈$0.177**, zero rate-limit/
   timeout/other errors across every model. Results:

   | Model | Accuracy | Cost/correct classification | p50 / p95 latency | Errors |
   |---|---|---|---|---|
   | mistral-3-14B | 85.7% | $0.00014 | 460ms / 676ms | none |
   | deepseek-4-flash | 85.0% | $0.00005 | 3891ms / 7809ms | none |
   | openai-gpt-oss-20b | 83.1% | $0.00010 | 1185ms / 3824ms | none |
   | glm-5.3-flash | 80.7%* | $0.00023* | 1614ms / 8574ms | 4 parse_error* |
   | openai-gpt-oss-120b | 81.4% | $0.00008 | 2523ms / 5873ms | none |
   | llama-4-maverick | 78.4% | $0.00014 | 1485ms / 2344ms | none |

   *(glm-5.3-flash row is the corrected number — see point 6.)*

6. **A second real finding, from the full run**: `glm-5.3-flash` hit 12/301
   (4%) `parse_error`s, all `finish_reason=length` — it was spending the full
   `max_output_tokens=1024` budget on chain-of-thought before ever emitting
   `{"label": ...}`. This is precisely the risk flagged as a `GUESS` in §4 below
   ("if a reasoning model ends up a finalist, 20/1024 tokens may truncate its
   reasoning") — now confirmed with real data rather than left as a hypothetical.
   Doubled the budget to 2048 (via `MAX_OUTPUT_TOKENS=2048` env var, no code
   change — this setting was already designed to be env-configurable) and
   re-ran just that model: parse errors dropped to 4/301 (1.3%), accuracy
   80.1%→80.7%. **Notable methodological detail**: the 4 issues that still
   failed at 2048 tokens (`#389, #817, #999, #1417`) are almost entirely
   *different* issues than the original 12 that failed at 1024 tokens (only
   `#817` appears in both lists) — at `temperature=0`, on the identical prompt,
   re-running produced a different subset of truncation failures. That's real,
   observed evidence for exactly the self-consistency risk flagged in §3's
   criterion 8 (`check_self_consistency.py`, built but not yet run): this
   model's reasoning length is not deterministic call-to-call even at temp=0,
   which is a genuine finding about `glm-5.3-flash` specifically, not a
   harness bug — worth raising in the review session as a concrete instance of
   "temperature=0 isn't a determinism guarantee."
7. **Total real SI spend across this entire smoke-test-then-full-run sequence:
   ≈$0.23.** Nothing was run against the real API without an explicit
   go-ahead at each stage, per the standing rule to confirm before any real
   spend, including small test runs.

**Read on the actual tradeoff, from real data**: `mistral-3-14B` (best
accuracy, cheapest+fastest by a wide margin, non-reasoning, dense) vs.
`deepseek-4-flash` (essentially tied accuracy, cheapest cost/correct, but
~8x the latency, MoE, reasoning) is the tradeoff the data actually supports —
small/fast/dense vs. cost-efficient/reasoning/slow. Notably, `deepseek-4-flash`'s
reasoning isn't buying meaningfully higher accuracy than `mistral-3-14B`'s
non-reasoning pass on this task, which is itself a data point for the "does
reasoning help fixed-schema classification" question raised in §3's framing
above.

### Self-consistency and rate-limit probes, 2026-09-10 — run on the two leading candidates

Ran both previously-built-but-unrun probes against `mistral-3-14B` and
`deepseek-4-flash` specifically (not all 6 — narrowed scope on purpose since
these two are the actual candidates in contention, per the discussion above).

**Self-consistency** (`check_self_consistency.py --model mistral-3-14B --model
deepseek-4-flash`; 30 issues × 3 repeats × 2 models = 180 calls, ≈$0.012 total):
both models are highly stable at `temperature=0` — **97% unanimous, 100%
majority** for both. No differentiator here; neither model exhibits the
flip-flopping risk this check was built to catch, at least on this sample.

**Rate-limit ceiling** (`probe_rate_limits.py`, concurrency 4/8/16/32, 40
calls/level, one model per invocation): this is where a real, material
difference showed up.

| Model | conc=4 | conc=8 | conc=16 | conc=32 |
|---|---|---|---|---|
| `mistral-3-14B` | 7.6 req/s, 0 errors | 16.7 req/s, 0 errors | 29.3 req/s, 0 errors | 30.4 req/s, 0 errors |
| `deepseek-4-flash` | 1.2 req/s, 0 errors | 1.7 req/s, 1/40 rate-limited | 2.8 req/s, 0 errors | 3.6 req/s, 2/40 rate-limited |

`mistral-3-14B` scales cleanly to 30+ req/s with zero errors at every level
tested (ceiling not yet found — would need levels beyond 32 to locate it).
`deepseek-4-flash` tops out an order of magnitude lower (~3.6 req/s) and is
already showing early rate-limiting at the levels tested. **This meaningfully
changes the practical read on the earlier tradeoff**: `deepseek-4-flash`'s
cost/correct advantage ($0.00005 vs mistral's $0.00014) only matters if you can
actually push volume through it — for the customer's stated "high volume
across many repos" framing, a ~3.6 req/s ceiling is a real constraint that a
raw cost-per-call number doesn't surface. `mistral-3-14B` now looks like the
stronger candidate on every axis measured except raw cost-per-correct-call,
which is precisely the kind of finding criterion 10 (throughput ceiling,
separate from latency) was added to catch.

### Final selection: `mistral-3-14B` + `deepseek-4-flash` — decided 2026-09-10

This is a real design decision, not a deferral — the exercise explicitly says
no single "right" pair is expected, only that the reasoning be articulable.
Numbers below are the full 301-issue screening results:

| | `mistral-3-14B` | `deepseek-4-flash` |
|---|---|---|
| Accuracy | **85.7%** | 85.0% |
| Cost/correct classification | $0.000136 | **$0.0000455** |
| p50 / p95 latency | **460ms / 676ms** | 3891ms / 7809ms |
| Self-consistency (unanimous/majority) | 97% / 100% | 97% / 100% (tied) |
| Throughput ceiling | **>30 req/s, 0 errors up to conc=32** | ~3.6 req/s, rate-limiting by conc=8 |
| Architecture | Dense, non-reasoning | MoE, dual reasoning/non-reasoning |

**`mistral-3-14B` wins outright on every axis except cost-per-call.** That
asymmetry is the finding, not a reason to pick a different, more "balanced"-
looking pair — this build's whole ground-truth methodology (§2) is built
around reporting real gaps plainly rather than smoothing them into a false
symmetry, and the same principle applies here.

**Why this pair is still the right comparison to show, not just the winner
alone**: naive per-token pricing makes `deepseek-4-flash` look like the
obvious choice (3x cheaper per correct classification) — and that's exactly
the kind of surface-level comparison a customer evaluating models by sticker
price would make. Real load testing reverses the recommendation: an ~8x
higher per-token cost is the price of an ~8x-plus higher throughput ceiling,
and for "high volume across many repos," throughput is the binding
constraint, not per-call price. **The value of running both probes wasn't
finding two similar models — it was catching that the cheaper-looking model
doesn't actually hold up at the volume the customer described.**

**Production recommendation**: `mistral-3-14B` as the default. `deepseek-4-flash`
named explicitly as the model to reconsider for a specific lower-volume
workload (a smaller repo, or a customer whose actual call volume sits well
under ~3 req/s) where its cost-per-token advantage would matter more than its
throughput ceiling — not dismissed outright, scoped to where it actually wins.

**Alternatives considered for the final pair, and why not chosen:**
- `openai-gpt-oss-20b` (83.1% acc, second-closest to mistral, genuinely
  reasoning-capable) — never run through the self-consistency/throughput
  probes. Swapping it in for the final recommendation would trade a
  fully-evidenced comparison for a partially-evidenced one, for no clear gain:
  the reasoning-vs-non-reasoning question this exercise names as "a good
  direction" is already answered by the deepseek comparison.
- `llama-4-maverick` (78.4% acc, 400B non-reasoning) — a real finding in its
  own right (a ~28x larger non-reasoning model scored *worse* and slower than
  the 14B dense model — "bigger doesn't help this task"), worth a side mention
  in the README, but it's a narrower insight than the reasoning-vs-throughput
  story above and doesn't hit the reasoning-vs-non-reasoning axis.
- `openai-gpt-oss-120b` (81.4% acc, ~117B MoE, reasoning-capable) — worse
  accuracy than its own smaller sibling `openai-gpt-oss-20b` (81.4% vs 83.1%)
  despite ~6x the parameters, a second "bigger doesn't help" data point,
  redundant with the `llama-4-maverick` finding. Worse than `deepseek-4-flash`
  on accuracy and latency both, with no probe evidence and no offsetting
  story — dominated, not a close call.
- `glm-5.3-flash` (80.7% acc, only after doubling `MAX_OUTPUT_TOKENS` to
  recover from 12/301 parse errors down to 4/301) — lowest accuracy of all 6
  screened, the only model with real errors remaining in the full screening
  run, and the model where a rerun at identical `temperature=0` settings
  produced a mostly *different* set of failures (§3 point 6) — real evidence
  of non-deterministic reasoning length, a reliability flag on top of already
  being the weakest on accuracy. No case for it as a finalist.
- A pair picked to look more evenly matched — rejected on principle, per the
  asymmetry note above.

**Pricing confirmed, 2026-09-10**: `deepseek-4-flash` is $0.07/M input,
$0.17/M output per the DO dashboard (Gradient AI Platform > Models) —
essentially the same as the $0.068/$0.168 placeholder that had been flagged as
unverified. The "cost-per-token vs. throughput" argument above holds: the
number itself was close to right, it was only the *id* that was wrong.
Nothing left blocking this recommendation.

### The prompt-length / caching tradeoff — decided, not automatic

DO applies prompt caching automatically for open-weight models, but (at least for
OpenAI-family models) only above a ~1,024-token prompt. Checked locally (no API
call): the actual system prompt in `prompt.py` is **~230 tokens** — well under
that threshold, so as currently written this workload gets no caching benefit
despite calling the same prompt 500+ times per model. Growing the prompt (e.g.
few-shot examples) would clear the threshold, but directly conflicts with the
earlier deliberate choice (§4 below) to keep the prompt minimal so the eval
measures raw zero-shot capability, not prompt-engineering. Decision: **keep the
prompt as-is, forgo the caching benefit, and say so explicitly** rather than
silently picking a side of this tradeoff.

---

## 4. Evaluation methodology

**Per-issue inference, never batched.** Directly required by the spec (the
customer needs per-call cost/latency, individually retryable failures, per-case
fallback routing) — batching would make every one of those requirements
impossible to satisfy, so there was no real tradeoff here, just a constraint to
implement correctly.

**Prompt design**: system prompt gives the model the exact same 6 class
definitions the exercise itself uses, requests strict JSON
(`{"label": "..."}`), `temperature=0`, `max_tokens=20` *(superseded — see the
2026-09-10 correction below; the app's real, current default is
`max_output_tokens=1024`, env-configurable)*.
- No few-shot examples. Considered adding a few examples per class to boost
  accuracy, especially for smaller/weaker models — deliberately left out
  because the more useful number for a customer is "what does this model do
  zero-shot, out of the box," not "what can prompt engineering squeeze out of
  it." Also keeps prompt tokens (and therefore cost) identical and minimal
  across every candidate model, which matters for a fair cost comparison.
- `max_tokens=20` is a real risk flagged, not a settled choice: if a reasoning
  model ends up one of the two finalists, 20 tokens may truncate its
  chain-of-thought before it emits a label. Revisit once the finalists are
  known — noted in code and here rather than silently left as a latent bug.
- Parsing: strict JSON first, then a regex scrape, then a bare-word match.
  Considered strict-JSON-only (reject anything else) as a "more honest" signal
  of instruction-following — rejected because a customer running this in
  production would want the harness to actually extract a usable label from a
  slightly-malformed response, not throw it away. The middle ground: try hard
  to parse, but if all three fail, that's a real `parse_error`, and it **still
  counts against accuracy** in the scored view rather than being silently
  dropped from the denominator — so a model that reliably ignores the format
  instruction doesn't get a free pass.

**Concurrency**: `asyncio.Semaphore`-bounded, configurable via env var/request
payload without a rebuild, default 8.
- `GUESS`, stated as one: 8 was picked before any real rate-limit information
  existed — high enough for reasonable throughput, low enough that a burst of
  429s doesn't cascade into a retry storm across the whole corpus. This is
  exactly the kind of number the review session should push on, and the honest
  answer is "revisit once real SI limits are known," not a confident
  justification for 8 specifically.
- The two models being compared run **concurrently with each other**
  (`asyncio.gather` of both model runs), not sequentially. Tradeoff: sequential
  would make the wall-clock/throughput numbers cleaner (no cross-model resource
  contention), but doubles total time-to-result for a single comparison.
  Chose concurrent because the two models are presumably independent SI
  deployments with independent quota — worth verifying once real behavior is
  known; if they turn out to share a backend quota, this could skew the
  latency comparison and would need to change to sequential.

**Retries**: exponential backoff via `tenacity`, retried only on
429/5xx/timeout — explicitly *not* retried on other 4xx errors, because a
malformed request (bad model ID, bad payload) will never succeed on retry, and
retrying it would waste time and money while masking a real bug as a transient
one.

**Error taxonomy**: `rate_limit` / `timeout` / `parse_error` / `other` — the
spec asks for exactly 3 (rate limit, timeout, other); `parse_error` was added
as a 4th because it's a materially different failure mode specific to LLM
classification. Lumping it into "other" would hide the difference between "the
model is bad at the task" and "the model won't follow the output format,"
which have completely different fixes (capability problem vs. prompt-engineering
problem) — a customer deciding what to do next needs that distinction visible.

**Metrics**:
- `None` (not `0.0`) for any class with zero ground-truth support in the scored
  set. This was a correctness bug I caught and fixed mid-build: without it,
  `documentation`/`other` would show a 0% recall that reads as "the model
  failed at this," when the true statement is "we never tested this at all."
  Conflating those two is the kind of thing that erodes trust with a customer
  once they notice it.
- **Cost per correct classification** as the headline cost number, not just
  cost per call. Raw cost-per-call ignores accuracy (a cheap-but-wrong model
  isn't actually good value); raw accuracy ignores cost. This composite is the
  one number that answers the customer's actual question in one shot. Only
  computed for the scored subset, since "correct" is undefined without ground
  truth — left as `None` for the unscored view rather than faked.
- **Confusion matrix, row-normalized** (percentage of the true-label row), not
  overall-count or column-normalized. Chose row-normalization because "of all
  real bugs, what fraction did the model correctly call bugs" is the more
  directly actionable read off a heatmap; precision (the column-direction
  question) is already reported separately in the per-class table, so
  row-normalizing the matrix avoids showing the same information twice in two
  different visual forms.
- **p50/p95 latency reported paired with the concurrency they were measured
  at** — a bare latency number is close to meaningless without knowing the load
  it was measured under; this was an explicit spec requirement, implemented as
  a `(value, concurrency)` pair everywhere latency appears rather than a bare
  number that could get quoted out of context later.

**Two more correctness bugs, caught in review 2026-09-11 (same family as the
`None`-vs-`0.0` bug above — silently-wrong-looking-right numbers)**:
- `summarize_model_run` was mapping every failed call (rate limit, timeout,
  parse error — anything with no `predicted_label`) into the confusion
  matrix as a prediction of the **`other`** *class*. The failure correctly
  counted against accuracy, but recording it as a genuine "other" prediction
  meant: (a) if a future ground-truth set ever includes real `other` examples,
  a model that merely got rate-limited on one of them would show up as
  coincidentally *correct*, and (b) every failure on an unrelated class
  quietly inflated `other`'s false-positive count, understating its precision
  for no real reason. Fixed by excluding failures from the confusion matrix
  entirely — support/recall still account for them via an independent
  per-class ground-truth count, so a failure still correctly costs the model
  recall on its true class, it just never gets attributed to a specific wrong
  (or coincidentally right) predicted class.
- `agreement_rate` and the per-issue `models_agree` flag both used a bare
  `predicted_label_a == predicted_label_b` comparison — since a failed call's
  `predicted_label` is `None`, two failures on the same issue compared equal
  and counted as the models *agreeing*, which is backwards (neither model
  said anything). Fixed to require both predictions to be non-`None`, and
  `agreement_rate` now also returns how many issues got excluded this way, so
  the UI states plainly what the headline percentage is silent on rather than
  hiding it.
- **Correction, 2026-09-11**: the note originally here claimed the
  already-persisted finalist run (`run_1789106490.json`) needed no changes —
  that was wrong for the agreement-rate bug. The confusion-matrix bug really
  was a no-op for this run (no failure landed on a true-`other` issue), but
  `agreement_rate`'s fix excludes an issue whenever *either* model failed, not
  only when both did — and this run has 7 single-sided failures (3 for
  `mistral-3-14B`, 4 for `deepseek-4-flash`), zero double-sided. Checking only
  for double-sided failures missed that the denominator itself needed to
  shrink. The persisted run's `agreement_rate` was stale at the old-semantics
  value (88.6% = 475/536) versus the corrected one (89.8% = 475/529) — fixed
  directly in the JSON (recomputed from its own `per_issue` rows, no re-run/no
  spend needed) and `agreement_excluded_count: 7` added. README's headline
  number updated to match. Regression tests added for both exact failure
  modes in `test_metrics.py`.

---

## 5. Cost, latency, throughput — reporting design

All of §4's metrics decisions apply here; the additional choice was **how the
run is executed and observed from the UI**:

**Async job + polling**, not a synchronous blocking request, not
websockets/SSE streaming.
- A full 536×2-issue run can take minutes — too long to safely hold open a
  single blocking HTTP request (real risk of a proxy/gateway timeout killing
  it partway through).
- Considered websockets/SSE for live per-issue progress — would give a nicer
  "37/536 done" progress bar, but adds real complexity (connection lifecycle,
  reconnect-on-drop handling) that isn't warranted for a tool one engineer uses
  to kick off one comparison at a time. Polling every 1.2s is the "boring but
  correct" choice for this scope.
- Named explicitly as a **production caveat**: this polling design, and the
  in-memory job dict it relies on, does not survive a container restart
  mid-run, and doesn't support multiple engineers watching independent runs at
  scale. Fine for this exercise; would need a real job queue (and the
  real datastore from §1) before this is a multi-user production tool.

---

## 6. Production handling (customer's broader workload)

Covered in full in the README; the key design choice here was **what NOT to
build**, per the spec's own instruction ("we are not asking you to build that
system, only to have thought through the path"):
- No fallback-model routing implemented — designed and argued for (route
  parse failures / low-confidence outputs to a larger model or back to the
  frontier model) but intentionally left as a described mechanism, not code,
  because the per-issue non-batched design already makes it *possible* to add
  without restructuring anything, and building it now would be solving a
  problem the exercise explicitly didn't ask for.
- No drift-monitoring, no multi-label support, no cross-repo label-schema
  reconciliation tooling — all named directly in the README as explicitly
  out of scope, with the reasoning for each (drift needs live production
  traffic to observe; multi-label would contradict the customer's own stated
  schema of "exactly one label"; cross-repo reconciliation is a real project
  in its own right, not a feature of this proving-ground exercise).

---

## 7. Testing approach

**Unit tests for pure-logic modules only** (label parsing, percentile math,
precision/recall/F1 including the None-vs-zero distinction, agreement rate) —
13 tests, no committed end-to-end test suite.
- Why: the parts most likely to have a quiet, hard-to-notice bug are exactly
  the small pure functions where a human eyeballing the UI wouldn't catch an
  off-by-one or a wrong edge case (e.g., the None-vs-0.0 semantics, which
  produced correct-*looking* wrong numbers before the fix).
- The UI itself was verified manually but for real this session: a headless
  Chromium driver actually clicked through every view (Scored/Unscored/
  Operational, the disagreement filter, the raw-output expand) against both
  the dev server and the built Docker container, screenshots inspected, console
  checked for errors. Considered committing that Playwright script as a
  permanent E2E test — didn't, because for a one-off take-home the manual
  verification (repeatable on demand, not running in CI) was judged sufficient
  evidence for the time invested, versus maintaining a browser-test harness
  that outlives the exercise.

---

## 8. Full list of deliberate scope cuts ("what I chose not to do")

Stated together here since the exercise explicitly grades this list:

- No authentication/authorization on the API (fine for a local demo; would be
  a hard requirement before real exposure).
- No real datastore — flat JSON files, single-writer, no concurrent-run
  support (named in §1 and §5 as the first thing to fix before scaling past
  one engineer / one repo at a time).
- No live per-issue progress streaming during a run — binary running/done
  status via polling only.
- No fallback-model routing implemented (designed, not built — §6).
- No multi-label classification — one label per issue, matching the
  customer's own stated schema, not a limitation I introduced.
- No ingestion of issue comments/discussion threads — title + body only, to
  stay within the "thin ingestion, a few hundred lines" instruction.
- No CI pipeline, no linter config beyond a `pyrightconfig.json` for editor
  sanity.
- No hardening of GitHub API pagination beyond a basic rate-limit-aware sleep —
  sufficient for a one-time ~536-issue pull, not for a continuously-syncing
  ingestion pipeline across many repos.

---

## 9. Everything still marked `PENDING`

For a quick final check before the review session — these are the only things
in the app that are not yet backed by real evidence:

- ~~The model shortlist screening~~ **DONE, 2026-09-10**: real screening run
  against the live SI catalog, 301 issues × 6 models, see §3 "Screening run
  process" above for the full results table and the two real bugs it caught
  (`deepseek-v4-flash` wrong id, `glm-5.3-flash` token-budget truncation).
- ~~The final two recommended models~~ **DONE, 2026-09-10**: `mistral-3-14B`
  (production default) + `deepseek-4-flash` (lower-volume alternative) — see
  §3 "Final selection" for the full rationale, alternatives rejected, and the
  self-consistency/rate-limit evidence behind it. UI default selection in
  `RunControls.jsx` updated to match.
- ~~Real pricing in `model_catalog.py` for `deepseek-4-flash`~~ **DONE,
  2026-09-10**: confirmed directly from the DO dashboard ($0.07/$0.17 per 1M
  input/output) — close to the original placeholder, only the id was wrong,
  not the number.
- ~~Spot-check `mistral-3-14B` pricing~~ **Partially done, 2026-09-10**: could
  not verify via the DO dashboard the way deepseek was — Mehjabeen doesn't have
  billing access (a DO admin added the account's credits), and the console's
  "Models" browse page doesn't list `mistral-3-14B` at all, only an unrelated
  older/dedicated-GPU model ("Mistral 7B Instruct v0.3"). Confirmed via the
  live `/v1/models` API directly that `mistral-3-14B` is real (not a
  wrong-id situation like deepseek was — it's produced ~500+ real, sensible
  completions today across the screening/consistency/rate-limit runs). A
  second, independent WebFetch of the public pricing page returned $0.20/$0.20
  per 1M tokens and correctly identified it as "Ministral 3 14B Instruct" —
  matching the existing `model_catalog.py` entry exactly (price and model
  identity both). Treat this as **corroborated by two independent lookups,
  not billing-confirmed** — a real step down from deepseek's dashboard-level
  confirmation, but the best available evidence given no billing access, and
  worth stating exactly this way (not overstated as "verified") if it comes up
  in the review session.
- ~~Whether `DEFAULT_CONCURRENCY=8` holds up~~ **Answered indirectly,
  2026-09-10**: `probe_rate_limits.py` ran against both finalists (§3) —
  `mistral-3-14B` handles concurrency up to 32 with zero errors;
  `deepseek-4-flash`'s real ceiling is much lower (~3.6 req/s, rate-limiting
  visible by concurrency=8). The **app's shared `DEFAULT_CONCURRENCY=8`**
  hasn't itself been changed — still worth deciding whether the real
  full-corpus run below should lower concurrency specifically when
  `deepseek-4-flash` is one of the two models being compared, or just accept
  some rate-limit retries as an honest part of that model's result.
- **Correction to an earlier PENDING note**: this doc previously listed
  `max_tokens=20` as the *app's* untested default — that was stale. The app's
  real default has been `max_output_tokens=1024` (env-configurable) since the
  null-content bug fix, well before today's screening run, and the screening
  run confirms `deepseek-4-flash` produces zero parse errors at that setting.
  Not an open risk for the final pair.
- ~~The real **full-corpus** comparison run~~ **DONE, 2026-09-10**: ran
  `mistral-3-14B` vs `deepseek-4-flash` on all 536 issues through the actual
  app's real API endpoint (`POST /api/jobs`, not the standalone screening
  script — same code path the UI's "Run comparison" button uses), at the
  app's default concurrency=8, real SI credits. Persisted as
  `data/runs/run_1789106490.json` (the old `run_1788828523.json` synthetic
  dry-run fixture was deleted — it used placeholder model ids and would have
  been misleading sitting next to the real result). Results: mistral 84.7%
  accuracy / $0.0567 total / 416ms p50 / 8.6 req/s / 3 rate-limited-out-of-536;
  deepseek 83.4% / $0.0193 / 2641ms p50 / 2.5 req/s / 4 rate-limited-out-of-536;
  agreement rate 89.8% (see the 2026-09-11 correction below — originally
  recorded as 88.6% under pre-fix agreement semantics). Full table and the
  honest note on why accuracy is
  ~1pt lower here than the screening pass (real non-determinism + a few
  retry-exhausted rate-limit misses, both predicted by the earlier probes) are
  in README.md's "Cost, latency, throughput" section — this doc doesn't
  duplicate it. This run is also what validated the real (non-dry-run) API
  path through the app actually works end-to-end, not just in `DRY_RUN=true`.
- ~~A deployed URL for the running application~~ **DONE, 2026-09-10**:
  https://doctl-issue-classifier.onrender.com/ — deployed on Render's free
  tier, from a private GitHub repo (`MehjabeenZ/doctl-issue-classifier`,
  personal account, kept separate from the work `gh`/git identity also on
  this machine — see the identity-separation notes this session for why that
  mattered). Smoke-tested live: triggered a real 1-issue comparison directly
  on the deployed instance (not just locally) — both models reached the real
  SI API successfully and returned correct classifications, confirming the
  live deploy's env vars/network egress actually work end-to-end, not just in
  local dev. Two real bugs caught before the push: `.gitignore` and
  `.dockerignore` both excluded `data/runs/`, which would have silently
  dropped the real persisted eval result from the repo and the deployed
  image — fixed both before pushing.

## 6. Second-pass independent review, 2026-09-11 — fixes applied

A second review (post-deployment, treating the live app as a reviewer would)
found several real issues. All fixed locally, no re-run/no spend required:

- **Critical — unauthenticated `POST /api/jobs` had no spend bounds.** The
  live deployment has `DRY_RUN=false` and a real billed SI key behind an
  endpoint anyone can call, with no bound on `concurrency`, `limit`, or which
  model ids were accepted, and a wildcard CORS origin. Fixed in
  `schemas.py` (`RunRequest` now validates `model_a`/`model_b` against
  `CATALOG`, bounds `concurrency` to 1-64 and `limit` to 1-536) and `main.py`
  (CORS restricted to the local dev origin only — the deployed frontend is
  same-origin and needs none; a single-flight in-process lock rejects a
  second job while one is running). This caps worst-case unattended spend to
  one bounded run at a time rather than leaving it unbounded. Not adding auth
  — the exercise wants a publicly runnable app, and these bounds address the
  actual risk (unbounded spend) without blocking that. Regression tests in
  `test_schemas.py`.
  - **Superseded, 2026-09-14 (first pass)**: bounding the endpoint still left
    it live for anyone to trigger *some* real spend. First fix: a
    `HOSTED_DEMO_READ_ONLY` flag that refused `POST /api/jobs` entirely on
    the hosted instance, serving the real persisted result read-only.
  - **Superseded again, 2026-09-14 (same day)**: the read-only gate traded
    away too much — re-reading the exercise, "the same code that produces
    the numbers you walk us through is the code we will run" reads as an
    expectation that reviewers can actually *run* the app, not just view a
    static result. A read-only hosted demo satisfies "not open to random
    spend" but not "reviewers can run it." Replaced with HTTP Basic Auth
    gating the whole app (`backend/app/auth.py`, `DemoBasicAuthMiddleware`,
    wired into `main.py`; `DEMO_USERNAME`/`DEMO_PASSWORD` in `config.py`,
    both empty by default so local/Docker runs are never gated). This gets
    both properties at once instead of trading one for the other: nobody
    without the credential can see or run anything (`render.yaml` sets both
    as `sync: false` secrets, shared with reviewers separately, never
    committed), and anyone *with* it gets the fully live, unrestricted app —
    same capability as running it locally, no separate "demo mode." Removed
    the read-only flag and its UI treatment (`App.jsx`/`RunControls.jsx`)
    entirely rather than keep both mechanisms — one gate is enough, and
    stacking a read-only mode behind an auth wall would just be confusing.
    The concurrency/limit/model-id bounds and single-flight lock from the
    first fix stay in place as defense-in-depth (an authenticated caller can
    still fat-finger a double-click, and it costs nothing to keep them).
    Considered a shared token/header scheme instead of Basic Auth — rejected
    because Basic Auth needs zero frontend code (every browser handles the
    credential prompt natively) where a token scheme would need a login form
    and header plumbing for no real security benefit at this scale.
- **High — `reconcile_ground_truth.py` didn't reproduce the checked-in
  `ground_truth.json`.** Rerunning it from the intermediate files would have
  folded the AI-double-labeled needs-labeling tier (217 rows) into
  `ground_truth.json` alongside the 301 maintainer-traceable rows — silently
  producing a ~518-row "ground truth" that contradicts the project's own
  stated principle (ground truth must trace to real doctl labels, not AI
  labeling) and the README's 301-row methodology. Also: nothing in the repo
  actually produced the checked-in `silver_labels_unscored.json` — it was an
  orphaned artifact. Fixed: the needs-labeling agreement tier now writes to
  `silver_labels_unscored.json` instead, `ground_truth.json` stays scoped to
  the maintainer-traceable tier only. Verified by actually running the fixed
  script against the checked-in intermediates: `ground_truth.json` came back
  **byte-identical** to what's checked in; `silver_labels_unscored.json` came
  back as the 217 auto-agreed rows (the checked-in 235-row file also has the
  18 human-adjudicated rows, which are a manual merge step by design — see
  the script's docstring — so the original 235-row file was restored rather
  than overwritten with the 217-row reproduction).
- **High — the persisted finalist run's `agreement_rate` used pre-fix
  semantics.** See the correction inline in §"Two more correctness bugs"
  above: `run_1789106490.json` was saved before the `agreement_rate` fix
  landed, and the fix excludes an issue whenever *either* model failed (this
  run has 7 single-sided failures, not caught by the earlier "no double
  failure" check). Recomputed directly from the run's own `per_issue` data
  (no API calls) — 88.6% → 89.8%, `agreement_excluded_count: 7` added.
  README updated to match.
- **Medium — confusion-matrix shading normalized by returned predictions,
  not by ground-truth support.** Since failed calls are excluded from the
  matrix entirely, a row with failures could shade as if every prediction
  landed correctly. Fixed `ConfusionMatrix.jsx` to normalize by `support`
  instead, and added an explicit "failed" column so a gap reads as missing
  data, not as an untouched cell.
- **Medium — "cost per correct" divides full-run cost by scored-subset
  correct count.** True of the metric as computed (`total_cost_usd` is over
  all 536 calls; `correct` is over the 301 scored issues) — a real
  full-workload economic number, but not literally "cost per correct
  classification" for one matched population. Left the computation as-is
  (the persisted run doesn't store per-issue cost, so there's no way to
  retroactively compute a scored-only figure without introducing the same
  artifact/code mismatch as the agreement-rate bug above) and relabeled it
  honestly instead: "Full-run cost / correct" with a caption stating the
  denominator population, in `OperationalMetrics.jsx`.
- **Medium — overclaimed accuracy/throughput language in the README.**
  "Mistral wins on accuracy" overstated a 16-vs-12-correct-issue gap (out of
  301, paired) that isn't established as significant without a test; "throughput
  ceiling" implied a measured hard limit when only `deepseek-4-flash` was
  actually driven into rate-limiting (`mistral-3-14B`'s ceiling was never
  found, only that it's above 30 req/s). Reworded to state what was actually
  measured and let latency/throughput (the real, large, unambiguous gaps)
  carry the recommendation instead of accuracy.
- **Medium — the deployed app showed an empty state, not the real result.**
  A reviewer opening the live URL had to trigger a new (real, billed) run
  just to see the app do anything, even though the finalist result was
  already persisted and served by `GET /api/runs`. Fixed: `App.jsx` now loads
  the most recent persisted run on mount; "Run comparison" is still available
  to run a fresh one.
- **Low — stale text in this doc.** The `max_tokens=20` mention in §4 is
  annotated as superseded (it already was corrected further down, just not
  where a top-to-bottom read would hit it first).
