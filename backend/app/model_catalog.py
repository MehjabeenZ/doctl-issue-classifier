"""Model pricing catalog — real data, pulled 2026-09-09.

Sourcing:
  - Model IDs, context length, max output tokens: live `GET {SI_BASE_URL}/models`
    (authoritative — this is literally what the API will accept).
  - Per-token pricing: scraped from docs.digitalocean.com/products/inference/details/pricing/
    (the API itself does not return price). An earlier scrape of this same page
    returned inconsistent model names/params across two fetches — this version came
    back as one complete, internally consistent 54-row table that matches the live
    model catalog's naming, so it's trusted as the working number, but it was NOT
    independently cross-checked against the billing dashboard UI. Spot-check the
    final two recommended models' prices in the dashboard before quoting them to a
    customer as final.
  - Open-weight / license verification: a research pass (WebSearch, 2026-09-09)
    against each candidate's model card / HF repo / release announcement — see
    DESIGN_DECISIONS.md for the full table and sources.

Only open-weight models are listed here — DigitalOcean's SI catalog also serves
closed/proprietary models (Anthropic Claude, OpenAI's GPT-5.x/o-series, and
Qwen3.8-Max's closed API track) through the same endpoint, which are explicitly
OUT OF SCOPE for this exercise regardless of being technically callable with this
key. `qwen3.8-max` is deliberately excluded even though DO hosts it: Alibaba shipped
it as a closed API first and only later open-weighted the underlying checkpoint
under a separate license, and it isn't confirmed which one DO is actually serving
under that model id — a cleaner same-size-class alternative (qwen3.5-397b-a17b,
confirmed Apache 2.0) exists, so there's no reason to carry that ambiguity.
`minimax-m2.5` is also excluded: it's open-weight per the license research, but it
doesn't appear on DO's public pricing page at all, so there's no honest cost number
to give it.
"""
from __future__ import annotations

import httpx

from app.config import settings


class ModelPricing:
    __slots__ = ("model_id", "input_per_million_usd", "output_per_million_usd", "notes", "release_risk")

    def __init__(
        self, model_id: str, input_per_million_usd: float, output_per_million_usd: float,
        notes: str = "", release_risk: str = "unassessed",
    ):
        self.model_id = model_id
        self.input_per_million_usd = input_per_million_usd
        self.output_per_million_usd = output_per_million_usd
        self.notes = notes
        # Deprecation/lifecycle risk, distinct from license legality — a dated
        # point-in-time snapshot (id ending in e.g. -0731) tends to get superseded
        # and pulled faster than a vendor's undated "current" release line, which
        # matters for a production recommendation: "low" = plain version name,
        # vendor's current line; "medium"/"high" = dated snapshot or fast-moving
        # release cadence, expect to re-validate/migrate sooner.
        self.release_risk = release_risk

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_million_usd
            + output_tokens / 1_000_000 * self.output_per_million_usd
        )


# The broader screening shortlist (see scripts/run_model_screening.py) — chosen to
# span org, architecture (dense vs MoE), size, and reasoning-vs-non-reasoning, while
# staying cheap enough to screen all of them against the scored set without denting
# the $200 budget. Not every confirmed-open-weight model in the catalog is here;
# the rest (Kimi K3, GLM-5.3 full, Nemotron Ultra, Qwen3.5-397B, DeepSeek V4 Pro,
# etc.) were reviewed and set aside for cost/redundancy reasons — see
# DESIGN_DECISIONS.md for the full reasoning.
CATALOG: dict[str, ModelPricing] = {
    "openai-gpt-oss-20b": ModelPricing(
        "openai-gpt-oss-20b", 0.05, 0.45,
        "~21B total/3.6B active MoE, Apache 2.0, reasoning (adjustable effort). Small/cheap end.",
        release_risk="low — plain version name, OpenAI's stable open-weight line",
    ),
    "openai-gpt-oss-120b": ModelPricing(
        "openai-gpt-oss-120b", 0.06, 0.39,
        "~117B total/5.1B active MoE, Apache 2.0, reasoning (adjustable effort). Same family as 20b, isolates size effect.",
        release_risk="low — plain version name, OpenAI's stable open-weight line",
    ),
    "mistral-3-14B": ModelPricing(
        "mistral-3-14B", 0.20, 0.20,
        "14B dense (Ministral 3 14B Instruct), Apache 2.0, non-reasoning baseline.",
        release_risk="low-medium — plain version name, but Mistral ships new generations frequently",
    ),
    "llama-4-maverick": ModelPricing(
        "llama-4-maverick", 0.20, 0.696,
        "400B total/17B active MoE, Llama 4 Community License, non-reasoning. Well-known reference point.",
        release_risk="low — plain version name, Meta's flagship line, historically long-supported",
    ),
    "deepseek-4-flash": ModelPricing(
        "deepseek-4-flash", 0.07, 0.17,
        "284B total/13B active MoE, MIT, dual Thinking/Non-Thinking modes. Cost-efficient large-MoE candidate. "
        "Picked over the dated 'deepseek-v4-flash-0731' snapshot: same model family, lower deprecation risk "
        "(undated 'current' line vs. a point-in-time checkpoint). "
        "PRICING CONFIRMED 2026-09-10 directly from the DO dashboard (Gradient AI Platform > Models > "
        "Deepseek V4 Flash / deepseek-4-flash): $0.07/M input, $0.17/M output. The earlier id mixup "
        "('deepseek-v4-flash' 404ing, corrected to 'deepseek-4-flash') is resolved, and the original "
        "placeholder numbers ($0.068/$0.168, sourced from an earlier flagged-as-unreliable WebFetch pass) "
        "turned out close to correct — off only in rounding, not in the number itself.",
        release_risk="low-medium — undated line, but DeepSeek ships new generations on a fast cadence",
    ),
    "glm-5.3-flash": ModelPricing(
        "glm-5.3-flash", 0.15, 0.50,
        "320B total/18B active MoE, MIT, hybrid sparse+linear attention. Different org (Z.ai) for diversity.",
        release_risk="medium — undated, but Z.ai's GLM line ships new major versions on a fast cadence",
    ),
}

# Reference only — other confirmed-open-weight candidates NOT in the screening
# shortlist, kept here so pricing is available if the shortlist needs to expand.
REFERENCE_CATALOG: dict[str, ModelPricing] = {
    "deepseek-3.2": ModelPricing("deepseek-3.2", 0.25, 0.80, "~671B total MoE, MIT, hybrid thinking."),
    "deepseek-v4-pro": ModelPricing("deepseek-v4-pro", 0.87, 1.74, "1.6T total/49B active MoE, MIT, reasoning."),
    "deepseek-v4-pro-0813": ModelPricing("deepseek-v4-pro-0813", 1.32, 3.96, "1.6T total/49B active MoE, MIT, reasoning."),
    "gemma-4-31B-it": ModelPricing("gemma-4-31B-it", 0.18, 0.50, "30.7B dense, Apache 2.0 (verify model card), reasoning-configurable."),
    "glm-5.2": ModelPricing("glm-5.2", 0.70, 2.20, "753B total/40B active MoE, MIT, reasoning by default."),
    "glm-5.3": ModelPricing("glm-5.3", 1.40, 4.40, "~744B total MoE, custom revenue-gated license, reasoning."),
    "kimi-k2.6": ModelPricing("kimi-k2.6", 0.95, 4.00, "1T total/32B active MoE, modified-MIT, reasoning w/ effort levels."),
    "kimi-k3": ModelPricing("kimi-k3", 2.55, 12.95, "2.8T total/104B active MoE, custom revenue-gated license, reasoning."),
    "qwen3.5-397b-a17b": ModelPricing("qwen3.5-397b-a17b", 0.55, 3.50, "397B total/17B active MoE, Apache 2.0, hybrid reasoning (/think /no_think)."),
    "nemotron-3-ultra-550b": ModelPricing("nemotron-3-ultra-550b", 0.90, 1.70, "550B total/~55B active, OpenMDW-1.1, open reasoning model."),
    "nemotron-3-nano-omni": ModelPricing("nemotron-3-nano-omni", 0.50, 0.90, "30B total/3B active, NVIDIA Open Model License, reasoning."),
    "nemotron-nano-12b-v2-vl": ModelPricing("nemotron-nano-12b-v2-vl", 0.20, 0.60, "12B dense, NVIDIA Open Model License, reasoning."),
    "mimo-v2.5-pro": ModelPricing("mimo-v2.5-pro", 0.40, 1.50, "1.02T total/42B active MoE, MIT, reasoning."),
}


async def refresh_from_live_api() -> list[str]:
    """Fetch the real list of model IDs this API key can access. Requires SI_API_KEY."""
    async with httpx.AsyncClient(base_url=settings.si_base_url, timeout=30) as client:
        resp = await client.get(
            "/models", headers={"Authorization": f"Bearer {settings.si_api_key}"}
        )
        resp.raise_for_status()
        return [m["id"] for m in resp.json()["data"]]


def get_pricing(model_id: str) -> ModelPricing:
    if model_id in CATALOG:
        return CATALOG[model_id]
    if model_id in REFERENCE_CATALOG:
        return REFERENCE_CATALOG[model_id]
    raise KeyError(
        f"No pricing entry for '{model_id}'. Add it to CATALOG or REFERENCE_CATALOG in "
        "model_catalog.py using the rate from the DO dashboard before running an eval against it."
    )
