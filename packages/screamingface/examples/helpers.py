import os

import httpx


def openrouter_credits(api_key: str | None = None) -> dict:
    """How much money is left on the OpenRouter key powering these runs.

    Reads OPENROUTER_KEY from the environment unless a key is passed —
    the AI Gateway's credential store is encrypted and write-only, so the
    notebook cannot read the connected key back out of it.
    """
    key = api_key or os.environ.get("OPENROUTER_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_KEY in the environment (or pass api_key=...)")
    try:
        response = httpx.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        remaining = data["total_credits"] - data["total_usage"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"OpenRouter credits lookup failed: {exc}") from exc
    print(
        f"OpenRouter: ${remaining:,.2f} remaining "
        f"(${data['total_usage']:,.2f} of ${data['total_credits']:,.2f} used)"
    )
    return data
