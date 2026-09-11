"""Verify SI_API_KEY is set and valid by hitting the real /v1/models endpoint.

Never prints the full key — only a masked preview — so it's safe to run and
share output from. Reads from a .env file at the repo root or the environment
(same precedence as the app itself, via app.config.Settings).

Usage:
    python3 scripts/check_si_key.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import settings  # noqa: E402
from app.model_catalog import refresh_from_live_api  # noqa: E402


def mask(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


async def main() -> None:
    if not settings.si_api_key:
        print("No SI_API_KEY found (checked .env and the environment). Set it and re-run.")
        return

    print(f"Using key: {mask(settings.si_api_key)}")
    print(f"Base URL:  {settings.si_base_url}")

    try:
        models = await refresh_from_live_api()
    except Exception as exc:  # noqa: BLE001 — this IS the error report, not swallowed
        print(f"AUTH FAILED: {exc}")
        return

    print(f"AUTH OK — {len(models)} models available on this key:")
    for m in models:
        print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
