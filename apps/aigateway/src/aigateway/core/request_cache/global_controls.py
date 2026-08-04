"""OME-305 per-request cache controls for the global cache (v2 grammar).

FEATURE: one global exact-request cache that is ON by default. Under v1 a caller
had to send ``cache: {"use-cache": true}`` to get any caching at all, which meant
the benchmark runs that most need it silently paid full price. Under v2 an
ordinary request participates in the global cache, and the control object exists
only to OPT OUT.

INVARIANT: the grammar is CLOSED and fail-safe. Exactly one field is understood
(``use-cache``); every other field — the retired v1 controls and anything
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

# Retired v1 controls. WHY they are named rather than merely falling into the
# unknown branch: they had real v1 semantics (a per-request TTL, a write
# suppression, a read suppression) that the global cache deliberately does not
# offer — v2 entries never expire and are shared by every caller. Bypassing is the
# only honest answer, and enumerating them keeps the acceptance test that proves
# it from drifting away from what v1 actually accepted.
LEGACY_CONTROL_FIELDS: Final[frozenset[str]] = frozenset(
    {"ttl", "s-maxage", "no-cache", "no-store"}
)

BYPASS_OPTED_OUT: Final = "opted_out"
BYPASS_MALFORMED_CONTROLS: Final = "malformed_controls"
BYPASS_UNSUPPORTED_CONTROL: Final = "unsupported_control"


@dataclass(frozen=True)
class GlobalCacheControls:
    """What the caller asked of the cache for THIS request.

    ``participate`` means both directions: read the global cache, and store a
    successful response in it. v2 has no read-only or write-only lane — a caller
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
