"""Translate Gateway web-search intent into OpenRouter's owned plugin envelope.

Callers never submit OpenRouter's extensible ``plugins`` object. They submit bounded standard
parameters, and this module assigns the native request shape documented at
https://openrouter.ai/docs/guides/features/plugins/web-search.
"""

from __future__ import annotations

from typing import Any

WEB_SEARCH_PARAM = "web_search"
WEB_SEARCH_EXCLUDED_DOMAINS_PARAM = "web_search_excluded_domains"

EXCLUDE_DOMAINS_KEY = "exclude_domains"
"""OpenRouter web-plugin spelling; its server-tool surface uses a different field name."""

_WEB_SEARCH_POLICY: dict[str, object] = {"id": "web", "engine": "native"}


def apply_web_search(body: dict[str, Any]) -> None:
    """Consume standard fields and assign OpenRouter's web-plugin envelope.

    INVARIANT (OME-781/D2): a pure function of ``body`` alone. The deployment
    blocklist that used to be unioned in here is gone — see the rationale in
    ``parameters.py`` above the search rules — so this must never regain a
    non-body input without re-opening that decision.
    """
    wanted = body.pop(WEB_SEARCH_PARAM, None)
    caller_excluded = body.pop(WEB_SEARCH_EXCLUDED_DOMAINS_PARAM, None) or []
    if wanted is not True:
        return

    excluded = sorted(set(caller_excluded))
    plugin = dict(_WEB_SEARCH_POLICY)
    if excluded:
        plugin[EXCLUDE_DOMAINS_KEY] = excluded

    # Assignment, never merge: caller-supplied plugin envelopes are refused by classification.
    body["plugins"] = [plugin]


__all__ = [
    "EXCLUDE_DOMAINS_KEY",
    "WEB_SEARCH_EXCLUDED_DOMAINS_PARAM",
    "WEB_SEARCH_PARAM",
    "apply_web_search",
]
