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
_ONLINE_MODEL_SUFFIX = ":online"


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
    suffix_enabled = _consume_online_model_suffix(body)
    if wanted is not True and (wanted is not None or not suffix_enabled):
        return

    excluded = sorted({*settings.web_search_excluded_domains, *caller_excluded})
    plugin = dict(_WEB_SEARCH_POLICY)
    if excluded:
        plugin[EXCLUDE_DOMAINS_KEY] = excluded

    # Assignment, never merge: caller-supplied plugin envelopes are refused by classification.
    body["plugins"] = [plugin]


def _consume_online_model_suffix(body: dict[str, Any]) -> bool:
    """Normalize OpenRouter's implicit-search model suffix into the guarded plugin path.

    ``:online`` enables retrieval upstream even when the caller never supplied
    :data:`WEB_SEARCH_PARAM`. Leaving the suffix intact would therefore bypass both deployment
    and caller exclusions. Removing it and emitting the same gateway-owned plugin used by the
    explicit flag gives both spellings one policy-enforced wire representation. An explicit
    ``web_search=false`` still wins: the suffix is removed and no plugin is emitted.
    """

    model = body.get("model")
    if not isinstance(model, str) or not model.endswith(_ONLINE_MODEL_SUFFIX):
        return False
    body["model"] = model.removesuffix(_ONLINE_MODEL_SUFFIX)
    return True


__all__ = [
    "EXCLUDE_DOMAINS_KEY",
    "WEB_SEARCH_EXCLUDED_DOMAINS_PARAM",
    "WEB_SEARCH_PARAM",
    "WebSearchSettings",
    "apply_web_search",
]
