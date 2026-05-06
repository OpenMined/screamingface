"""LiteLLM pre-call hook that injects per-provider auth headers.

LiteLLM normally expects an `api_key` in env or router config. We instead
look up the active provider plugin's `OAuthStrategy` at call time and
merge its headers into `kwargs["extra_headers"]`. This keeps OAuth
ownership entirely inside our gateway while still letting LiteLLM do the
provider routing and response shaping.

Wired in `main.py` via `litellm.input_callback.append(oauth_pre_call)`.
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import ProviderRegistry

logger = logging.getLogger(__name__)


def make_oauth_pre_call(registry: ProviderRegistry):
    async def oauth_pre_call(kwargs: dict[str, Any]) -> None:
        provider = kwargs.get("custom_llm_provider")
        if not provider:
            return
        plugin = registry.get(provider)
        if plugin is None:
            return
        strategy = plugin.oauth_strategy()
        if strategy is None:
            return
        try:
            headers = await strategy.get_authorization_header()
        except Exception:
            logger.exception("oauth strategy for %s failed", provider)
            return
        merged = dict(kwargs.get("extra_headers") or {})
        merged.update(headers)
        kwargs["extra_headers"] = merged

    return oauth_pre_call
