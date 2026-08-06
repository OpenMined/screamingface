"""Translate Gateway web-search intent into OpenRouter's owned plugin envelope.

Callers never submit OpenRouter's extensible ``plugins`` object. They submit bounded standard
parameters, and this module assigns the native request shape documented at
https://openrouter.ai/docs/guides/features/plugins/web-search.
"""

from __future__ import annotations

from typing import Any, Protocol

WEB_SEARCH_PARAM = "web_search"
WEB_SEARCH_EXCLUDED_DOMAINS_PARAM = "web_search_excluded_domains"

EXCLUDE_DOMAINS_KEY = "exclude_domains"
"""OpenRouter web-plugin spelling; its server-tool surface uses a different field name."""

_WEB_SEARCH_POLICY: dict[str, object] = {"id": "web", "engine": "native"}


class WebSearchSettings(Protocol):
    """The deployment policy needed to prepare an OpenRouter request."""

    web_search_excluded_domains: list[str]


def apply_web_search(body: dict[str, Any], settings: WebSearchSettings) -> None:
    """Consume standard fields and assign OpenRouter's web-plugin envelope.

    Deployment and caller exclusions are unioned, so a caller cannot remove an operator's
    requested exclusions. Upstream support remains model/engine-specific; a benchmark requiring
    hard exclusion must choose a compatible Engine route.
    """
    wanted = body.pop(WEB_SEARCH_PARAM, None)
    caller_excluded = body.pop(WEB_SEARCH_EXCLUDED_DOMAINS_PARAM, None) or []
    if wanted is not True:
        return

    excluded = sorted({*settings.web_search_excluded_domains, *caller_excluded})
    plugin = dict(_WEB_SEARCH_POLICY)
    if excluded:
        plugin[EXCLUDE_DOMAINS_KEY] = excluded

    # Assignment, never merge: caller-supplied plugin envelopes are refused by classification.
    body["plugins"] = [plugin]


__all__ = [
    "EXCLUDE_DOMAINS_KEY",
    "WEB_SEARCH_EXCLUDED_DOMAINS_PARAM",
    "WEB_SEARCH_PARAM",
    "WebSearchSettings",
    "apply_web_search",
]
