"""OME-479 detailed ``/v1/model-parameters`` document composition (app layer).

FEATURE: profile-bound detailed parameter contract. Overlays a provider plugin's
OWN observations with its OWN gateway rules (the SAME rule source as the
``/v1/models`` summary) into the locked v1 document, and derives the opaque
``contract_id`` / ``context.revision`` digests.

INVARIANT (purity): this composer takes no clock and does no I/O. ``freshness``
and the opaque ``context_identity`` token are supplied by the caller, so the
document is a deterministic function of its inputs — which is what lets the
digests be reproducible and testable.

INVARIANT (privacy): the digests are one-way SHA-256 over non-secret identity and
version inputs. The raw inputs — account ids, connection ids, credential names,
secrets — are hashed, never echoed, so they cannot be recovered from the output.

INVARIANT (SOLID/hexagonal): no provider-name switch and no central inventory
live here; the plugin selects its rules/observations/tools/transport and this
module only composes them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .chat_parameters import compose_contract_entries, normalize_rules

if TYPE_CHECKING:
    from .chat_parameters import (
        ParameterProjectionRule,
        ParameterSchema,
        ProviderParameterObservation,
        ToolCapability,
        TransportCapability,
    )
    from .profile_models import AuthType

SCHEMA_VERSION = 1

_CONTRACT_ID_PREFIX = "pc_"
_CONTEXT_REVISION_PREFIX = "ctx_"
# Unit separator: forbidden in every digest input (ids, paths, enums), so joined
# fields cannot collide across differently-structured inputs.
_SEP = "\x1f"
_DIGEST_HEX = 40


def upstream_model_id(canonical_id: str) -> str:
    """Return the model-author id: the canonical id minus its owning provider.

    WHY: derived from the canonical public id (AIGateway namespace), never from a
    LiteLLM transport prefix such as ``ollama_chat/`` (plan 4.1).
    """
    return canonical_id.split("/", 1)[1] if "/" in canonical_id else canonical_id


def _sha(parts: Iterable[str]) -> str:
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()


def _schema_key(schema: ParameterSchema | None) -> str:
    # WHY: fold the VALIDATION SCHEMA into the revision so a range/enum/type change
    # moves the contract id even when the hand-authored projection_revision string is
    # unchanged. Canonical (sorted keys) + order-independent; empty when absent.
    if schema is None:
        return ""
    return json.dumps(schema.to_json_schema(), sort_keys=True, separators=(",", ":"))


def _rules_revision(rules: tuple[ParameterProjectionRule, ...]) -> str:
    # INVARIANT: the gateway projection revision changes when a rule is added,
    # removed, or revised — INCLUDING a change to its validation schema (range,
    # enum, type) — so the contract id always moves with dispatch behavior.
    return _sha(
        f"{r.request_path}|{r.projection_kind}|{r.cache_behavior}|{r.projection_revision}"
        f"|{','.join(r.applicable_auth_modes)}|{_schema_key(r.parameter_schema)}"
        for r in rules  # normalized: deterministically ordered, one per path
    )


def _evidence_revision(observations: Iterable[ProviderParameterObservation]) -> str:
    # The provider evidence revision changes when any observed field/support/
    # source/staleness changes. Sorted so input order is irrelevant.
    return _sha(
        sorted(f"{o.request_path}|{o.support}|{o.source}|{int(o.stale)}" for o in observations)
    )


def _opaque_id(prefix: str, tag: str, inputs: tuple[str, ...]) -> str:
    # ``tag`` is domain separation so contract_id and context.revision are
    # distinct values even though both hash the same input set (and both move
    # when ANY input changes).
    return prefix + _sha((tag, *inputs))[:_DIGEST_HEX]


def build_model_parameter_document(
    *,
    canonical_id: str,
    gateway_provider: str,
    auth_mode: AuthType,
    scope: str,
    context_identity: str,
    rules: Iterable[ParameterProjectionRule],
    observations: Iterable[ProviderParameterObservation],
    tools: Iterable[ToolCapability],
    transport: Iterable[TransportCapability],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    """Compose the locked v1 detailed contract for one (model, profile) context."""
    normalized = normalize_rules(rules)
    observations = tuple(observations)

    projection_revision = _rules_revision(normalized)
    evidence_revision = _evidence_revision(observations)
    digest_inputs = (
        canonical_id,
        auth_mode,
        scope,
        context_identity,
        evidence_revision,
        projection_revision,
        str(SCHEMA_VERSION),
    )

    entries = compose_contract_entries(normalized, observations, auth_mode=auth_mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": _opaque_id(_CONTRACT_ID_PREFIX, "contract", digest_inputs),
        "model": {
            "id": canonical_id,
            "gateway_provider": gateway_provider,
            "upstream_id": upstream_model_id(canonical_id),
        },
        "context": {
            "scope": scope,
            "auth_mode": auth_mode,
            "revision": _opaque_id(_CONTEXT_REVISION_PREFIX, "context", digest_inputs),
        },
        "freshness": freshness,
        "parameters": {entry.request_path: entry.to_detail_dict() for entry in entries},
        "tools": {tool.tool_type: tool.to_dict() for tool in tools},
        "transport": {cap.name: cap.to_dict() for cap in transport},
    }
