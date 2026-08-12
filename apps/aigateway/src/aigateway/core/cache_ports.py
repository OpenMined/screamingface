"""OME-305 cache-projection port vocabulary.

FEATURE: one global exact-request cache shared by every hosted user. A cache key
can only be built when the provider can describe its own output-affecting
preparation *purely* — no I/O, no identity, no credential. This module owns the
two names that port is written in.

INVARIANT (SOLID/hexagonal): this is a LEAF. It imports nothing from
``aigateway``, so the provider port (``core.plugin_base``), the key builder
(``core.request_cache.global_keys``) and the route can all name ONE bypass type
without a cycle — and without the port layer having to import the cache
persistence package (Tortoise models, secret store) merely to describe itself.

AIDEV-NOTE: ``core.request_cache.global_keys`` re-exports this type so providers,
the key builder and the route all use the same closed bypass vocabulary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

# The ONE reason a projection failure is ever reported as. WHY it is clamped to a
# single constant rather than echoing what the provider said: this string is
# published in a response header, so it must come from a closed vocabulary the
# gateway owns — a provider-composed message could carry a model name, an
# upstream error or a caller value.
PROJECTION_BYPASS_REASON: Final = "provider_projection"

# The cache subsystem could not be consulted at all. Distinct from every reason above: those
# describe a request that CANNOT
# be cached, this one describes a cache that cannot be reached. The request itself is
# fine and is served by the provider.
#
# INVARIANT: this is a BYPASS, never a miss and never a request failure. Reporting it
# as a miss would invite a write to a store that just failed to read.
CACHE_UNAVAILABLE_REASON: Final = "cache_unavailable"

# Every value ``X-AIGW-Cache-Reason`` may ever carry, from every layer that can emit
# one: this module, ``request_cache.global_eligibility``,
# ``request_cache.global_controls``, ``request_cache.global_keys`` and
# ``request_cache.global_plan``.
#
# WHY the strings are spelled out here instead of imported from those modules: this
# module is a LEAF by design (see the module docstring) and importing them would
# invert the dependency and create a cycle. The cost of duplication is paid back by
# ``test_global_cache_reason_vocabulary``, which asserts this set is EXACTLY the set
# of reason constants those modules define — so a new reason that is not published
# here fails a test rather than reaching an operator's header.
#
# WHY a single published set at all: the failure mode is a reason string invented at
# a call site and never published anywhere, which an operator then greps for and
# finds in no source of truth. One name enumerates the whole surface.
PUBLISHED_CACHE_REASONS: Final[frozenset[str]] = frozenset(
    {
        # this module
        "provider_projection",
        "cache_unavailable",
        # the operator gate (global_plan)
        "disabled",
        # the caller's control grammar (global_controls)
        "opted_out",
        "malformed_controls",
        "unsupported_control",
        # request eligibility (global_eligibility)
        "unsupported_shape",
        "unknown_parameter",
        "unsupported_fields",
        "malformed_parameter",
        "mode_restricted_parameter",
        "unprojected_parameter",
        "provider_rule_set",
        "stream",
        "metadata",
        # canonicalization (global_keys)
        "canonicalization_failure",
    }
)


@dataclass(frozen=True)
class CacheBypass:
    """This request cannot be represented exactly, so it is not cached at all.

    INVARIANT: ``reason`` is drawn from the CLOSED vocabulary published above as
    ``PUBLISHED_CACHE_REASONS``, because it is emitted to callers in the
    ``X-AIGW-Cache-Reason`` header. It never carries a caller value, a prompt
    fragment, a provider error message or any identity.
    """

    reason: str


# WHY a named alias rather than the inline signature at every call site: the
# route, the key builder and every plugin must agree that the projection is a
# PURE function of the request body alone. Naming the shape makes an added
# parameter — an account id, a credential, an auth mode — a type error rather
# than a quiet leak of identity into a globally shared key.
type GlobalCacheProjection = Callable[[dict[str, Any]], dict[str, Any] | CacheBypass]
