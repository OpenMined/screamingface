"""OME-305 global exact-request fingerprint.

FEATURE: one global exact-request cache shared by every hosted user. This builder
keys the COMPLETE effective output-affecting model call — prompt,
every parameter a provider rule declares ``keyed``, and the provider's own pure
projection of what it will actually send — and nothing else.

STORY: as a benchmark operator I re-run the same suite from a second account and
the identical calls are answered from the first run's stored responses, with no
second provider dispatch and no access to the second account's credential.

INVARIANT: identity is structurally absent. There is no account, profile, user,
auth-mode or credential parameter anywhere in this module, and the provider
projection port is a function of the request body alone. That is what makes one
row safe to share globally.

INVARIANT: built from the hardened effective request after profile defaults are
merged body-wins, and before auth-mode resolution, the auth-specific classifier,
``prepare_chat_body`` and credential injection.

INVARIANT: fail safe, never fail loud. Every path that cannot be represented
EXACTLY — an unknown parameter, a rule that declares ``bypass``, a value that
fails its schema, a non-finite number, an unserializable value, a provider
projection that is absent, malformed or raising — returns a ``CacheBypass`` with
a reason from the closed ``BYPASS_*`` vocabulary. The cache is an optimization
and must never become an availability dependency, so nothing here raises into the
request path and nothing here performs I/O.

AIDEV-NOTE: THIS module is the public surface. Which request facts participate
lives in ``.global_eligibility`` and the caller's opt-out grammar lives in
``.global_controls``, both split out only to respect the repository's 450-line
limit; every name they own is re-exported here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from ..cache_ports import PROJECTION_BYPASS_REASON, CacheBypass, GlobalCacheProjection
from ..chat_parameters import ParameterProjectionRule
from .global_eligibility import (
    ABSENT,
    BYPASS_DECLARED,
    BYPASS_MALFORMED_PARAMETER,
    BYPASS_METADATA,
    BYPASS_MODE_RESTRICTED,
    BYPASS_RULE_SET,
    BYPASS_STREAM,
    BYPASS_UNKNOWN_PARAMETER,
    BYPASS_UNPROJECTED_NATIVE,
    BYPASS_UNSUPPORTED_SHAPE,
    EXCLUDED_TRANSPORT_FIELDS,
    PRESENCE_BYPASS_REASONS,
    PROMPT_FIELDS,
    STRUCTURALLY_EXCLUDED_FIELDS,
    TRUTHY_BYPASS_REASONS,
    collect_request_facts,
    is_text,
)

__all__ = [
    "ABSENT",
    "BYPASS_CANONICALIZATION",
    "BYPASS_DECLARED",
    "BYPASS_MALFORMED_PARAMETER",
    "BYPASS_METADATA",
    "BYPASS_MODE_RESTRICTED",
    "BYPASS_RULE_SET",
    "BYPASS_STREAM",
    "BYPASS_UNKNOWN_PARAMETER",
    "BYPASS_UNPROJECTED_NATIVE",
    "BYPASS_UNSUPPORTED_SHAPE",
    "EXCLUDED_TRANSPORT_FIELDS",
    "KEY_REVISION",
    "OPERATION",
    "PARAMETER_CONTRACT_REVISION",
    "PRESENCE_BYPASS_REASONS",
    "PROJECTION_BYPASS_REASON",
    "PROMPT_FIELDS",
    "STRUCTURALLY_EXCLUDED_FIELDS",
    "TRUTHY_BYPASS_REASONS",
    "CacheBypass",
    "CanonicalizationError",
    "GlobalCacheKeyResult",
    "GlobalCacheProjection",
    "GlobalChatCacheKey",
    "build_global_cache_key",
    "build_global_cache_key_dto",
    "canonical_key_material",
]

# INVARIANT: the revision is INSIDE the hashed material. Changing fingerprint semantics abandons
# old entries without coupling cache invalidation to a persisted database lane discriminator.
KEY_REVISION: Final = "aigw-global-chat-cache-2026-08"
OPERATION: Final = "chat.completions"
# WHY a gateway-wide revision on top of each rule's own ``projection_revision``:
# some output-affecting behaviour lives in the PIPELINE rather than in any single
# rule (how a wrapper is unpacked, which fields are excluded as transport). Bump
# this when that changes, and every existing entry is abandoned rather than
# re-served under new semantics.
#
# WHY the "b" bump (OME-782): tools/tool_choice moved from a blanket presence
# bypass to ordinary per-rule keying (D1). That is exactly the class of pipeline
# behaviour change this revision exists to cover, so the bump abandons any entry
# that was ever keyed (or would have bypassed) under the old tools-bypass
# contract rather than silently re-serving it under the new one.
PARAMETER_CONTRACT_REVISION: Final = "aigw-parameter-contract-2026-08b"

BYPASS_CANONICALIZATION: Final = "canonicalization_failure"

# Bounded recursion: a JSON body cannot be cyclic, but a provider projection is
# ordinary Python and could hand back something self-referential. Cap the walk so
# a buggy plugin costs a bypass instead of a recursion crash on the request path.
_MAX_DEPTH: Final = 64


class CanonicalizationError(ValueError):
    """Key material cannot be canonicalized to one deterministic byte string."""


@dataclass(frozen=True)
class GlobalChatCacheKey:
    """The closed set of facts a global key is computed from.

    INVARIANT: closed. Construction rejects an unknown member (there is no
    ``variant``, no sampling lane and no accounting field), and
    ``canonical_key_material`` renders exactly these members plus the two
    constants — so a new key dimension cannot be introduced by accident, and an
    existing one cannot be dropped from the hash while still being validated.

    AIDEV-NOTE: there is deliberately NO member for provider-native caller values.
    A native control's spelling is not what reaches the provider — the boundary
    reconstructs and normalizes it — so its effective value participates through
    ``prepared_request``. See ``global_eligibility._accept`` for the full rationale
    and the guard that keeps it from becoming a silent omission.
    """

    provider: str
    requested_model: str
    resolved_model: str
    messages: list[Any]
    system: Any
    keyed_parameters: dict[str, Any]
    prepared_request: Mapping[str, Any]
    parameter_contract_revision: str
    provider_adapter_revision: str


@dataclass(frozen=True)
class GlobalCacheKeyResult:
    """What the route may hold, log and persist.

    INVARIANT: hashes and non-sensitive provenance ONLY. The prompt and the
    canonical DTO exist as locals inside this module and are never returned, so
    neither can be logged or written to a row (plan §10).
    """

    key_hash: str
    prompt_hash: str
    provider: str
    model: str


def _canonical_json(value: Any) -> str:
    # INVARIANT: the exact canonical form (plan §2.5). ``sort_keys`` makes object
    # key order irrelevant while arrays keep theirs; ``separators`` removes
    # insignificant whitespace; ``ensure_ascii=False`` keeps prompt text byte-exact
    # rather than escaping it; ``allow_nan=False`` refuses the non-JSON literals.
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _system_member(system: Any) -> dict[str, Any]:
    # WHY a discriminated wrapper instead of omitting the member: a marker VALUE
    # could collide with a caller's real ``system`` string, and omitting the member
    # would make the closed member set conditional. This keeps "absent" unforgeable
    # and the shape fixed.
    if system is ABSENT:
        return {"present": False}
    return {"present": True, "value": system}


def _canonical_mapping(dto: GlobalChatCacheKey) -> dict[str, Any]:
    # ``schema`` and ``operation`` are derived rather than stored so they cannot
    # drift from the constants this module publishes.
    return {
        "schema": KEY_REVISION,
        "operation": OPERATION,
        "provider": dto.provider,
        "requested_model": dto.requested_model,
        "resolved_model": dto.resolved_model,
        "messages": dto.messages,
        "system": _system_member(dto.system),
        "keyed_parameters": dto.keyed_parameters,
        "prepared_request": dto.prepared_request,
        "parameter_contract_revision": dto.parameter_contract_revision,
        "provider_adapter_revision": dto.provider_adapter_revision,
    }


def _require_json_safe(value: Any, *, depth: int) -> None:
    """Reject anything ``json.dumps`` would coerce, reorder or refuse.

    WHY this exists on top of ``allow_nan=False``: ``json.dumps`` silently COERCES
    a non-string object key, so ``{1: "a"}`` and ``{"1": "a"}`` would canonicalize
    to the same bytes and share one cache entry. A wrong hit is the one failure
    mode this cache may never have, so anything ambiguous is refused instead.
    """
    if depth > _MAX_DEPTH:
        raise CanonicalizationError("key material is nested too deeply")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("key material holds a non-finite number")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _require_json_safe(item, depth=depth + 1)
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("key material holds a non-string object key")
            _require_json_safe(nested, depth=depth + 1)
        return
    # Type NAME only — never the value, which could be prompt text or a secret.
    raise CanonicalizationError(f"key material holds an unsupported type: {type(value).__name__}")


def canonical_key_material(dto: GlobalChatCacheKey) -> str:
    """The exact byte string that is hashed.

    INVARIANT: in-memory only. Never logged, never persisted, never returned to a
    caller — it contains the prompt verbatim. Public for tests and diagnostics.
    """
    mapping = _canonical_mapping(dto)
    _require_json_safe(mapping, depth=0)
    return _canonical_json(mapping)


# WHY the cache writes the FULL-CALL digest into ``prompt_hash`` instead of a prompt-only
# one: the column has no read path at all, and a prompt-only unsalted SHA-256
# would be a confirmation ORACLE over the public benchmark prompt set — anyone with
# database read access but no encryption key could hash a candidate prompt and learn
# whether it had been asked, without decrypting a single response. Writing the
# whole-call digest removes that at zero cost and keeps the column non-null, so no
# schema change is needed.
#
# INVARIANT: this is the ``key_hash`` value, not a second digest to keep in sync.


def build_global_cache_key_dto(
    *,
    provider: str,
    body: Mapping[str, Any],
    rules: Iterable[ParameterProjectionRule],
    projection: GlobalCacheProjection,
    provider_auth_modes: Iterable[str],
    parameter_contract_revision: str = PARAMETER_CONTRACT_REVISION,
) -> GlobalChatCacheKey | CacheBypass:
    """Assemble the closed key DTO for a hardened caller request, or bypass.

    ``provider_auth_modes`` is provider metadata, never caller identity — see
    ``collect_request_facts``.

    WHY it is REQUIRED rather than defaulted to empty: an empty set is a subset of
    every rule's applicable modes, so a default would make the mode-restriction
    guard silently inert for any caller that forgot it — a guard that passes its own
    tests and protects nothing. Required means the type checker refuses the omission.
    """
    if not isinstance(body, Mapping) or not is_text(provider):
        return CacheBypass(BYPASS_UNSUPPORTED_SHAPE)
    facts = collect_request_facts(
        body=body, rules=rules, projection=projection, provider_auth_modes=provider_auth_modes
    )
    if isinstance(facts, CacheBypass):
        return facts
    return GlobalChatCacheKey(
        provider=provider,
        requested_model=facts.requested_model,
        resolved_model=facts.resolved_model,
        messages=facts.messages,
        system=facts.system,
        keyed_parameters=facts.keyed_parameters,
        prepared_request=facts.prepared_request,
        parameter_contract_revision=parameter_contract_revision,
        provider_adapter_revision=facts.provider_adapter_revision,
    )


def build_global_cache_key(
    *,
    provider: str,
    body: Mapping[str, Any],
    rules: Iterable[ParameterProjectionRule],
    projection: GlobalCacheProjection,
    provider_auth_modes: Iterable[str],
    parameter_contract_revision: str = PARAMETER_CONTRACT_REVISION,
) -> GlobalCacheKeyResult | CacheBypass:
    """The global key for one explicit model call, or the reason it is not cached.

    INVARIANT: no identity parameter exists on this signature.
    ``provider_auth_modes`` is what the PROVIDER offers, not what this caller is
    using, so two different callers sending the identical explicit request still
    reach the identical hash — which is the whole point of a globally shared row.
    """
    dto = build_global_cache_key_dto(
        provider=provider,
        body=body,
        rules=rules,
        projection=projection,
        provider_auth_modes=provider_auth_modes,
        parameter_contract_revision=parameter_contract_revision,
    )
    if isinstance(dto, CacheBypass):
        return dto
    try:
        canonical = canonical_key_material(dto)
        key_hash = _sha256(canonical)
    except (CanonicalizationError, TypeError, ValueError):
        return CacheBypass(BYPASS_CANONICALIZATION)
    return GlobalCacheKeyResult(
        key_hash=key_hash,
        prompt_hash=key_hash,
        provider=dto.provider,
        model=dto.requested_model,
    )
