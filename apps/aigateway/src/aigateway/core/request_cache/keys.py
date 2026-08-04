"""Cache key canonicalization, eligibility, and per-request control parsing.

The v1 key is deliberately narrow: only ``model``, ``messages``, and a
top-level ``system`` participate in the prompt hash. Any other
output-affecting field makes the request ineligible (bypass) instead of
risking a wrong hit against a response produced with different parameters.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

KEY_VERSION = "aigw-chat-cache-v1"

# Part of the prompt hash. Everything else is either ignored or a bypass.
_PROMPT_FIELDS = ("model", "messages", "system")
# PUBLIC (OME-479 §4.6): the ONLY request paths THIS (v1) key builder can key. A rule
# declaring any ``cache_behavior`` other than ``bypass`` for a path outside this set
# publishes a promise the v1 pipeline cannot deliver.
#
# AIDEV-NOTE (OME-305, ruling 32): this used to claim the set was "locked by the
# registry conformance sweep". It is NOT, and no longer could be — that sweep moved to
# the v2 sets in ``global_keys`` (``PROMPT_FIELDS``, ``EXCLUDED_TRANSPORT_FIELDS``,
# ``PRESENCE_BYPASS_REASONS``, ``TRUTHY_BYPASS_REASONS``) when keying stopped being
# prompt-only. Nothing sweeps this constant now. Do not restore the claim: a comment
# asserting a guard that does not exist is worse than no comment, because the next
# reader will trust it instead of checking.
PROMPT_KEY_FIELDS: frozenset[str] = frozenset(_PROMPT_FIELDS)
# Transport/auth fields that never affect provider output. ``cache`` is the
# gateway's own control object and is popped before eligibility runs; it is
# listed defensively in case a caller re-injects it.
_IGNORED_FIELDS = frozenset({"timeout", "api_key", "extra_headers", "cache"})


@dataclass(frozen=True)
class CacheKeyResult:
    key_hash: str
    prompt_hash: str
    normalized_prompt: dict[str, Any]
    profile_name: str
    provider: str
    model: str


@dataclass(frozen=True)
class CacheBypass:
    reason: str


@dataclass(frozen=True)
class CacheControls:
    """Parsed per-request ``cache`` body controls (LiteLLM-shaped names)."""

    use_cache: bool = False
    ttl: int | None = None
    s_maxage: int | None = None
    no_cache: bool = False
    no_store: bool = False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def parse_cache_controls(body: dict[str, Any]) -> CacheControls:
    """Pop and parse the ``cache`` control object from a request body.

    The field is removed unconditionally so it can never reach provider
    plugins; malformed values parse as "not requested".
    """
    raw = body.pop("cache", None)
    if not isinstance(raw, dict):
        return CacheControls()
    return CacheControls(
        use_cache=raw.get("use-cache") is True,
        ttl=_positive_int(raw.get("ttl")),
        s_maxage=_positive_int(raw.get("s-maxage")),
        no_cache=raw.get("no-cache") is True,
        no_store=raw.get("no-store") is True,
    )


def build_cache_key(
    *,
    account_id: str,
    profile_name: str,
    provider: str,
    normalized_body: dict[str, Any],
) -> CacheKeyResult | CacheBypass:
    """Build the account/profile/provider/model-scoped cache key, or bypass.

    ``normalized_body`` is the provider-facing body after profile defaults and
    ``prepare_chat_body`` but before credential injection.
    """
    if not isinstance(normalized_body, dict):
        return CacheBypass(reason="unsupported_fields")

    if normalized_body.get("stream"):
        return CacheBypass(reason="stream")

    model = normalized_body.get("model")
    messages = normalized_body.get("messages")
    if not isinstance(model, str) or not model or not isinstance(messages, list):
        return CacheBypass(reason="unsupported_fields")

    for field in normalized_body:
        if field in _PROMPT_FIELDS or field in _IGNORED_FIELDS:
            continue
        if field == "stream":  # stream=False is reachable here and harmless
            continue
        return CacheBypass(reason="unsupported_fields")

    normalized_prompt: dict[str, Any] = {"model": model, "messages": messages}
    if "system" in normalized_body:
        normalized_prompt["system"] = normalized_body["system"]

    prompt_hash = _sha256(_canonical_json(normalized_prompt))
    key_hash = _sha256(
        _canonical_json(
            {
                "v": KEY_VERSION,
                "account_id": account_id,
                "profile_name": profile_name,
                "provider": provider,
                "model": model,
                "prompt_hash": prompt_hash,
            }
        )
    )
    return CacheKeyResult(
        key_hash=key_hash,
        prompt_hash=prompt_hash,
        normalized_prompt=normalized_prompt,
        profile_name=profile_name,
        provider=provider,
        model=model,
    )
