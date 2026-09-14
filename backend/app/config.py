from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    """All runtime knobs live here so they're env-configurable without a rebuild
    (per the exercise's concurrency requirement, extended to everything else too)."""

    si_api_key: str = ""
    si_base_url: str = "https://inference.do-ai.run/v1"

    default_concurrency: int = 8
    request_timeout_s: float = 90.0
    max_retries: int = 3
    retry_backoff_base_s: float = 1.0

    # Several open-weight candidates (DeepSeek V3.2/V4, gpt-oss, GLM, Qwen3.5, Nemotron,
    # Kimi) are reasoning models that emit chain-of-thought before the final label —
    # a low max_tokens would silently truncate them before they ever produce
    # {"label": ...}, understating their accuracy for a reason that has nothing to do
    # with classification capability. Sized generously; the actual cost impact is
    # negligible since output-token price is what's multiplied, not always spent.
    max_output_tokens: int = 1024

    # When true, the inference client returns synthetic responses instead of calling
    # the SI API. Lets the whole harness (retries, metrics, UI) be exercised and
    # demoed before real API credits exist.
    dry_run: bool = False

    # When true, POST /api/jobs is refused — the hosted deployment serves the
    # real persisted finalist result read-only instead of letting an anonymous
    # visitor trigger a fresh, credential-backed run. The app itself is still
    # fully live-runnable: this only gates the *hosted* instance. Run the
    # container locally (or flip this off) with a real SI_API_KEY to execute a
    # live comparison — see README "Run it yourself".
    hosted_demo_read_only: bool = False

    data_dir: str = "data"

    # Absolute path so this resolves the same whether the app is run from the
    # repo root, backend/, or inside the container (where it simply won't exist
    # and env vars passed to `docker run` take over instead).
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")


settings = Settings()
