"""OME-479 contract value types and rule algebra.

FEATURE: effective model-capability contract. This module owns the immutable
value objects and the *pure* derivations that turn a provider-local rule set
into the two client-facing projections:

- the conservative, profile-independent inline ``/v1/models`` summary, and
- the overlaid, profile-bound detailed ``/v1/model-parameters`` entries.

INVARIANT: provider *observation* (raw support) and gateway *rule* (what the
gateway validates and forwards) are separate concerns. Only a gateway rule
authorizes dispatch; an observation never does. Presence, provider support,
staleness, or an unknown enum value never authorize a parameter.

INVARIANT (SOLID/hexagonal): this module contains NO provider-name switch and
NO central provider inventory. Each plugin owns and selects its own rules; the
algebra here is provider-agnostic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .profile_models import AuthType

# Public enums (fail-closed: Pydantic rejects any value outside these literals).
ProviderSupport = Literal["supported", "conditional", "unsupported", "unknown"]
GatewayStatus = Literal["enabled", "disabled"]
CacheBehavior = Literal["keyed", "bypass", "transport_only"]
ProjectionKind = Literal["direct", "provider_native"]

# request paths are dotted identifier segments: "temperature", "provider_params.top_k".
_REQUEST_PATH_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
_WRAPPER_PREFIX = "provider_params."
_DISABLED_UNPROJECTED_REASON = "projection_not_implemented"


class ParameterRuleError(ValueError):
    """Base class for parameter-rule construction/derivation failures."""


class InvalidParameterRuleError(ParameterRuleError):
    """A single rule is internally inconsistent (fail closed at construction)."""


class DuplicateParameterRuleError(ParameterRuleError):
    """Two rules claim the same request path within one provider rule set."""


class ParameterValidationError(ValueError):
    """A caller-supplied value violates its gateway-owned schema."""


# Type names ParameterSchema can validate. A tuple of these expresses a
# TOP-LEVEL union (e.g. ``stop`` is string | array[string]); "object" and
# "array" are structural container types.
_SCHEMA_TYPE = Literal["number", "integer", "string", "boolean", "array", "object"]
_ITEM_TYPE = Literal["number", "integer", "string", "boolean", "object"]

# INVARIANT: bool subclasses int, so a boolean must never satisfy a numeric schema.
# Single source of per-type predicates, shared by top-level and array-item checks.
_TYPE_PREDICATES: dict[str, Any] = {
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


class ParameterSchema(BaseModel):
    """A bounded, gateway-owned validation schema for one request path.

    Deliberately small and dependency-free (no jsonschema): enough to validate
    the OpenAI-compatible params the gateway forwards — scalars, typed arrays,
    top-level objects, and top-level type UNIONS (e.g. ``stop`` is string |
    array[string]) — and to render a JSON-Schema fragment for the detailed
    contract.

    INVARIANT (shallow by design): validation proves the TOP-LEVEL shape and,
    for objects / array items, an optional single-key discriminator (used to
    gate ``tools[].type`` and object-form ``tool_choice`` against a provider's
    enabled tool types). Nested function definitions, JSON-Schema bodies, and
    tool names are LiteLLM/provider concerns and are intentionally NOT modelled.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # A single type, or a tuple of types for a top-level union.
    type: _SCHEMA_TYPE | tuple[_SCHEMA_TYPE, ...]
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[str, ...] | None = None
    item_type: _ITEM_TYPE | None = None
    # Optional single-key discriminator: when the value (or each array item) is an
    # object, its ``object_discriminator`` key must be in ``object_discriminator_enum``
    # (gates tools[].type fail-closed). Both fields are set together, or neither.
    object_discriminator: str | None = None
    object_discriminator_enum: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _check_schema_consistency(self) -> ParameterSchema:
        # INVARIANT: a schema that can match nothing, or a half-specified
        # discriminator, is a provider-config error — fail closed at construction.
        if isinstance(self.type, tuple) and not self.type:
            raise ValueError("type union must be non-empty")
        has_disc = self.object_discriminator is not None
        has_enum = self.object_discriminator_enum is not None
        if has_disc != has_enum:
            raise ValueError(
                "object_discriminator and object_discriminator_enum must be set together"
            )
        if has_disc:
            if not self.object_discriminator_enum:
                raise ValueError("object_discriminator_enum must be non-empty")
            # A discriminator only means something when the value or its items
            # can be an object.
            if "object" not in self._type_options and self.item_type != "object":
                raise ValueError("object_discriminator requires an object-capable type")
        return self

    @property
    def _type_options(self) -> tuple[str, ...]:
        return (self.type,) if isinstance(self.type, str) else self.type

    def to_json_schema(self) -> dict[str, Any]:
        rendered_type: Any = self.type if isinstance(self.type, str) else list(self.type)
        out: dict[str, Any] = {"type": rendered_type}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.enum is not None:
            out["enum"] = list(self.enum)
        if self.item_type is not None:
            out["items"] = {"type": self.item_type}
        # WHY: the discriminator is a gateway-side validation constraint, not part
        # of the published shape — the allowed values (e.g. a provider's enabled
        # tool types) are advertised in the contract's own tools section, so
        # embedding them here too would duplicate the source of truth. Keep the
        # rendered fragment purely structural.
        return out

    def validate_value(self, value: Any) -> None:
        """Raise ParameterValidationError when ``value`` violates this schema."""
        options = self._type_options
        if not any(_TYPE_PREDICATES[name](value) for name in options):
            raise ParameterValidationError(f"expected one of {options}")
        if isinstance(value, list):
            self._validate_items(value)
            if self.item_type == "object" and self.object_discriminator is not None:
                for item in value:
                    self._check_discriminator(item)
        elif isinstance(value, dict) and self.object_discriminator is not None:
            self._check_discriminator(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ParameterValidationError("below minimum")
            if self.maximum is not None and value > self.maximum:
                raise ParameterValidationError("above maximum")
        if self.enum is not None and value not in self.enum:
            raise ParameterValidationError("not an allowed value")

    def _check_discriminator(self, obj: dict[str, Any]) -> None:
        # obj is a dict; key/enum set together (construction guard); guard narrows type.
        key = self.object_discriminator
        allowed = self.object_discriminator_enum
        if key is None or allowed is None:
            return
        if obj.get(key) not in allowed:
            raise ParameterValidationError("object discriminator value not allowed")

    def _validate_items(self, value: list[Any]) -> None:
        if self.item_type is None:
            return
        check = _TYPE_PREDICATES[self.item_type]
        if not all(check(item) for item in value):
            raise ParameterValidationError("array item has wrong type")


class ParameterProjectionRule(BaseModel):
    """Synchronous, provider-owned dispatch policy for one request path.

    A rule is the ONLY thing that enables a parameter. Dynamic discovery never
    creates or enables one.
    """

    # WHY: the wire/constructor key stays "schema" (locked contract + client
    # API) via alias, while the python attribute is renamed so it no longer
    # shadows pydantic BaseModel.schema(). Callers pass schema=...; code reads
    # instance.parameter_schema.
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_path: str
    parameter_schema: ParameterSchema | None = Field(default=None, alias="schema")
    applicable_auth_modes: tuple[AuthType, ...]
    projection_kind: ProjectionKind
    provider_target: str | None = None
    cache_behavior: CacheBehavior
    output_affecting: bool = True
    projection_revision: str

    @field_validator("request_path")
    @classmethod
    def _valid_request_path(cls, value: str) -> str:
        if not _REQUEST_PATH_RE.match(value):
            raise InvalidParameterRuleError(f"invalid request_path: {value!r}")
        return value

    @field_validator("applicable_auth_modes")
    @classmethod
    def _normalize_auth_modes(cls, value: tuple[AuthType, ...]) -> tuple[AuthType, ...]:
        if not value:
            raise InvalidParameterRuleError("applicable_auth_modes must be non-empty")
        # Deterministic: sorted + deduplicated so equal rules hash/compare equal.
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def _check_consistency(self) -> ParameterProjectionRule:
        # INVARIANT: transport_only is reserved for separately reviewed transport
        # controls; an ordinary output-affecting field can never claim it.
        if self.output_affecting and self.cache_behavior == "transport_only":
            raise InvalidParameterRuleError("output-affecting rule cannot be transport_only")
        if self.projection_kind == "provider_native":
            if not self.request_path.startswith(_WRAPPER_PREFIX):
                raise InvalidParameterRuleError(
                    "provider_native rule must use a provider_params.* request_path"
                )
            if not self.provider_target:
                raise InvalidParameterRuleError("provider_native rule requires a provider_target")
        return self

    @property
    def target(self) -> str:
        """Where the validated value lands in the provider body."""
        return self.provider_target or self.request_path


class ProviderParameterObservation(BaseModel):
    """Raw provider evidence for one request path. Never authorizes dispatch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_path: str
    support: ProviderSupport
    source: str
    stale: bool = False
    parameter_schema: ParameterSchema | None = Field(default=None, alias="schema")


class ProviderDiscoverySnapshot(BaseModel):
    """A provider's discovered evidence, endpoint- and model-scoped kept separate.

    # INVARIANT (§5.1): endpoint evidence (what the API accepts syntactically) and
    # per-model evidence (what one model supports) are held in SEPARATE fields, so
    # they can never be conflated into a single support verdict for a path.
    # INVARIANT: discovery NEVER enables a parameter — a rule does. This snapshot is
    # evidence a caller overlays onto rules; on its own it authorizes nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_revision: str
    endpoint_observations: tuple[ProviderParameterObservation, ...] = ()
    model_observations: tuple[ProviderParameterObservation, ...] = ()


class ToolCapability(BaseModel):
    """Accepted ``tools[].type`` discriminator value + its gateway status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_type: str
    provider_support: ProviderSupport
    gateway_status: GatewayStatus

    def to_dict(self) -> dict[str, Any]:
        # Detailed contract reports every tool with its status (the summary
        # reports only enabled types — see ``supported_tool_types``).
        return {"provider_support": self.provider_support, "gateway_status": self.gateway_status}


class TransportCapability(BaseModel):
    """A transport control (e.g. ``stream``) reported separately from params."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    provider_support: ProviderSupport
    gateway_status: GatewayStatus
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "provider_support": self.provider_support,
            "gateway_status": self.gateway_status,
        }
        if self.reason is not None:
            out["reason"] = self.reason
        return out


class ParameterContractEntry(BaseModel):
    """One composed row of the detailed contract (observation + gateway rule)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_path: str
    parameter_schema: ParameterSchema | None = Field(alias="schema")
    provider_support: ProviderSupport
    provider_source: str
    provider_stale: bool
    gateway_status: GatewayStatus
    gateway_projection: str | None
    gateway_reason: str | None
    cache_behavior: CacheBehavior
    applicable_auth_modes: tuple[AuthType, ...]

    def to_detail_dict(self) -> dict[str, Any]:
        gateway: dict[str, Any] = {"status": self.gateway_status}
        if self.gateway_status == "enabled":
            gateway["projection"] = self.gateway_projection
        else:
            gateway["reason"] = self.gateway_reason
        gateway["cache_behavior"] = self.cache_behavior
        return {
            "request_path": self.request_path,
            "schema": (
                self.parameter_schema.to_json_schema()
                if self.parameter_schema is not None
                else None
            ),
            "provider": {
                "support": self.provider_support,
                "source": self.provider_source,
                "stale": self.provider_stale,
            },
            "gateway": gateway,
        }


# --- pure rule algebra -------------------------------------------------------


def normalize_rules(
    rules: Iterable[ParameterProjectionRule],
) -> tuple[ParameterProjectionRule, ...]:
    """Return rules deterministically ordered by request_path, rejecting dups.

    INVARIANT: one request path == at most one rule per provider rule set, so
    the summary and the detailed contract cannot disagree about a path.
    """
    ordered = sorted(rules, key=lambda rule: rule.request_path)
    seen: set[str] = set()
    for rule in ordered:
        if rule.request_path in seen:
            raise DuplicateParameterRuleError(f"duplicate rule for {rule.request_path!r}")
        seen.add(rule.request_path)
    return tuple(ordered)


def inline_supported_parameters(
    rules: Iterable[ParameterProjectionRule],
    *,
    available_auth_modes: tuple[AuthType, ...],
) -> tuple[str, ...]:
    """Conservative profile-independent summary.

    A path is included iff its rule is enabled under EVERY auth mode the
    provider offers (intersection). This prevents ``/v1/models`` from
    overclaiming an auth-specific field that only one mode can prove.

    INVARIANT: with NO auth mode available the summary is EMPTY. ``∅ ⊆ anything``
    is vacuously true, so the plain intersection would advertise every ruled path —
    the exact opposite of conservative. Nothing can be proven, so nothing is shown.
    """
    available = set(available_auth_modes)
    if not available:
        return ()
    return tuple(
        sorted(
            {rule.request_path for rule in rules if available <= set(rule.applicable_auth_modes)}
        )
    )


def supported_tool_types(tools: Iterable[ToolCapability]) -> tuple[str, ...]:
    """Sorted accepted tool-type values whose gateway status is enabled."""
    return tuple(sorted({tool.tool_type for tool in tools if tool.gateway_status == "enabled"}))


def compose_contract_entries(
    rules: Iterable[ParameterProjectionRule],
    observations: Iterable[ProviderParameterObservation],
    *,
    auth_mode: AuthType,
) -> tuple[ParameterContractEntry, ...]:
    """Overlay provider observations with gateway rules for one auth mode.

    - A rule applicable to ``auth_mode`` produces an ENABLED entry.
    - An observed-but-unruled path produces a DISABLED entry with
      ``projection_not_implemented`` — visible, but never dispatchable.
    """
    enabled_rules = {
        rule.request_path: rule for rule in rules if auth_mode in rule.applicable_auth_modes
    }
    observed = {obs.request_path: obs for obs in observations}
    entries: list[ParameterContractEntry] = []
    for path in sorted(set(enabled_rules) | set(observed)):
        rule = enabled_rules.get(path)
        obs = observed.get(path)
        if rule is not None:
            entries.append(
                ParameterContractEntry(
                    request_path=path,
                    schema=rule.parameter_schema or (obs.parameter_schema if obs else None),
                    provider_support=obs.support if obs else "unknown",
                    provider_source=obs.source if obs else "none",
                    provider_stale=obs.stale if obs else False,
                    gateway_status="enabled",
                    gateway_projection=rule.projection_kind,
                    gateway_reason=None,
                    cache_behavior=rule.cache_behavior,
                    applicable_auth_modes=rule.applicable_auth_modes,
                )
            )
            continue
        # obs is not None here (path came from the observed set).
        assert obs is not None
        entries.append(
            ParameterContractEntry(
                request_path=path,
                schema=obs.parameter_schema,
                provider_support=obs.support,
                provider_source=obs.source,
                provider_stale=obs.stale,
                gateway_status="disabled",
                gateway_projection=None,
                gateway_reason=_DISABLED_UNPROJECTED_REASON,
                cache_behavior="bypass",
                applicable_auth_modes=(),
            )
        )
    return tuple(entries)
