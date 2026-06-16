"""Gateway-owned opt-in response cache for deterministic chat completions.

Keying, eligibility, and persistence live here so ``routes/chat.py`` stays
orchestration-only. Cache policy is gateway-wide (not per provider plugin),
keys are computed before credential injection, and stored payloads are
encrypted at rest through the active secret store.
"""

from __future__ import annotations

from .keys import (
    CacheBypass,
    CacheControls,
    CacheKeyResult,
    build_cache_key,
    parse_cache_controls,
)
from .store import RequestCacheStore, RequestCacheWrite, TortoiseRequestCacheStore

__all__ = [
    "CacheBypass",
    "CacheControls",
    "CacheKeyResult",
    "RequestCacheStore",
    "RequestCacheWrite",
    "TortoiseRequestCacheStore",
    "build_cache_key",
    "parse_cache_controls",
]
