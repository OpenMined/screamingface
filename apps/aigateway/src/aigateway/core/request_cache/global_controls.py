"""OME-305 per-request controls for the global exact-request cache.

FEATURE: one global exact-request cache that is ON by default. An ordinary request
participates, and the control object exists only to OPT OUT.

INVARIANT: the grammar is CLOSED and fail-safe. Exactly one field is understood
(``use-cache``); every other field — unsupported controls and anything
unrecognized — makes the request bypass entirely rather than being ignored. A
caller who asks for a per-request TTL must not silently receive a permanent
global entry instead.

INVARIANT: ``cache`` is removed from the body UNCONDITIONALLY, including when it
is malformed, so a gateway control object can never reach a provider as if it
were a model parameter.

AIDEV-NOTE: the operator gate is separate and unchanged — ``request_cache_enabled``
still defaults to ``False`` in code and is turned on deliberately in hosted
config. This module decides only what the CALLER asked for.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

CONTROL_FIELD: Final = "cache"
USE_CACHE_FIELD: Final = "use-cache"

# Controls this cache deliberately does not offer. Bypassing is the only honest answer when a
# caller asks for a per-request TTL or one-way read/write behavior.
UNSUPPORTED_CONTROL_FIELDS: Final[frozenset[str]] = frozenset(
    {"ttl", "s-maxage", "no-cache", "no-store"}
)

BYPASS_OPTED_OUT: Final = "opted_out"
BYPASS_MALFORMED_CONTROLS: Final = "malformed_controls"
BYPASS_UNSUPPORTED_CONTROL: Final = "unsupported_control"


@dataclass(frozen=True)
class GlobalCacheControls:
    """What the caller asked of the cache for THIS request.

    ``participate`` means both directions: read the global cache, and store a
    successful response in it. There is no read-only or write-only lane — a caller
    that wants neither opts out, and there is nothing else to express.
    """

    participate: bool
    bypass_reason: str = ""


_PARTICIPATE: Final = GlobalCacheControls(participate=True)


def _refuse(reason: str) -> GlobalCacheControls:
    return GlobalCacheControls(participate=False, bypass_reason=reason)


def parse_global_cache_controls(body: dict[str, Any]) -> GlobalCacheControls:
    """Pop and interpret the ``cache`` control object.

    Absent, ``null`` or an empty object all state nothing, so the default applies
    and the request participates.
    """
    raw = body.pop(CONTROL_FIELD, None)
    if raw is None:
        return _PARTICIPATE
    if not isinstance(raw, Mapping):
        return _refuse(BYPASS_MALFORMED_CONTROLS)
    if set(raw) - {USE_CACHE_FIELD}:
        # INVARIANT: an unsupported field wins over a present ``use-cache: true``.
        # The caller asked for something this cache cannot honor; serving them a
        # global entry anyway would answer a different question than they asked.
        return _refuse(BYPASS_UNSUPPORTED_CONTROL)
    if USE_CACHE_FIELD not in raw:
        return _PARTICIPATE
    requested = raw[USE_CACHE_FIELD]
    if not isinstance(requested, bool):
        return _refuse(BYPASS_MALFORMED_CONTROLS)
    return _PARTICIPATE if requested else _refuse(BYPASS_OPTED_OUT)
