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

from .profile_models import AuthMode

# Public enums (fail-closed: Pydantic rejects any value outside these literals).
ProviderSupport = Literal["supported", "conditional", "unsupported", "unknown"]
GatewayStatus = Literal["enabled", "disabled"]
CacheBehavior = Literal["keyed", "bypass", "transport_only"]
ProjectionKind = Literal["direct", "provider_native"]

# request paths are dotted identifier segments: "temperature", "provider_params.top_k".
_REQUEST_PATH_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
_WRAPPER_PREFIX = "provider_params."
_DISABLED_UNPROJECTED_REASON = "projection_not_implemented"
# Sibling of the above, for the TRANSPORT section: the provider may well support
# the control upstream, but this gateway does not carry it yet.
_DISABLED_TRANSPORT_REASON = "gateway_transport_not_implemented"
# WHY a THIRD reason rather than reusing the first: "the gateway has no projection
# for this path" and "the gateway has a reviewed projection this CREDENTIAL cannot
# use" are different facts with different remedies — the first waits on gateway
# work, the second is fixed by connecting the other auth mode. Collapsing them
# tells a client to wait for something that already exists.
_DISABLED_AUTH_MODE_REASON = "projection_not_available_for_auth_mode"
# The transport control's name is the REQUEST FIELD callers actually send, so a
# client can act on what it reads. ``stream`` is gateway-owned (see
# ``GATEWAY_OWNED_FIELDS``), hence never expressible as a parameter rule — the
# transport section is its only possible home.
STREAM_TRANSPORT_NAME = "stream"


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
SchemaType = Literal["number", "integer", "string", "boolean", "array", "object"]
SchemaItemType = Literal["number", "integer", "string", "boolean", "object"]

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
    type: SchemaType | tuple[SchemaType, ...]
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[str, ...] | None = None
    item_type: SchemaItemType | None = None
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
    applicable_auth_modes: tuple[AuthMode, ...]
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
    def _normalize_auth_modes(cls, value: tuple[AuthMode, ...]) -> tuple[AuthMode, ...]:
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
    # Lifecycle, TRI-STATE on purpose (OME-647): True/False are verdicts a source
    # actually made, ``None`` means the source does not model lifecycle at all.
    # WHY not a plain ``bool``: a per-model catalog that lists supported parameter
    # NAMES has said nothing about deprecation, and defaulting it to False would
    # publish "the provider affirms this field is current" on evidence that does
    # not exist. An OpenAPI document, by contrast, does speak: a property it
    # carries without a ``deprecated`` flag is declared current, so that source
    # legitimately emits False.
    deprecated: bool | None = None


class ProviderToolObservation(BaseModel):
    """Raw provider evidence for one ``tools[].type``. Never authorizes dispatch.

    # WHY no ``source``/``stale`` twin of ``ProviderParameterObservation``: the
    # tools section publishes only ``provider_support`` + ``gateway_status``
    # (``ToolCapability.to_dict``), and a provider that reports a tool verdict also
    # projects it onto the ``tools``/``tool_choice`` request paths — which DO carry
    # provenance. Duplicating it here would be state the document never renders.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_type: str
    support: ProviderSupport


class ProviderDiscoverySnapshot(BaseModel):
    """A provider's discovered evidence, endpoint- and model-scoped kept separate.

    # INVARIANT (§5.1): endpoint evidence (what the API accepts syntactically) and
    # per-model evidence (what one model supports) are held in SEPARATE fields, so
    # they can never be conflated into a single support verdict for a path. Tool
    # evidence is a third, distinct field for the same reason — it feeds a different
    # published section and must not be merged into a request-path verdict.
    # INVARIANT: discovery NEVER enables a parameter — a rule does. This snapshot is
    # evidence a caller overlays onto rules; on its own it authorizes nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_revision: str
    endpoint_observations: tuple[ProviderParameterObservation, ...] = ()
    model_observations: tuple[ProviderParameterObservation, ...] = ()
    tool_observations: tuple[ProviderToolObservation, ...] = ()


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


def stream_transport_capability(*, gateway_enabled: bool) -> TransportCapability:
    """The ``stream`` transport control, derived from the gateway's own policy.

    FEATURE: discoverable transport contract. ``/v1/chat/completions`` rejects
    ``stream: true`` for a provider that cannot stream through this gateway;
    publishing that decision here is what lets a client read the policy instead of
    discovering it from a 400.

    INVARIANT: ``gateway_status`` carries POLICY, ``provider_support`` carries
    EVIDENCE, and the two are not the same claim. The gateway knows its own
    streaming decision; it has observed nothing about the upstream, so support
    stays ``unknown``. A plugin holding real evidence overrides the hook rather
    than having this factory invent it.

    AIDEV-NOTE: this reports an ALREADY-ENFORCED behaviour and enables nothing —
    which is why it needs no provider-transform proof. Keep it that way: if a
    control is ever published here BEFORE the dispatch path honours it, the
    contract starts lying.
    """
    return TransportCapability(
        name=STREAM_TRANSPORT_NAME,
        provider_support="unknown",
        gateway_status="enabled" if gateway_enabled else "disabled",
        reason=None if gateway_enabled else _DISABLED_TRANSPORT_REASON,
    )


class ParameterContractEntry(BaseModel):
    """One composed row of the detailed contract (observation + gateway rule)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_path: str
    parameter_schema: ParameterSchema | None = Field(alias="schema")
    provider_support: ProviderSupport
    provider_source: str
    provider_stale: bool
    # Published as ``provider.deprecated``; ``None`` when no source spoke. Defaulted
    # so a provider that models no lifecycle constructs entries unchanged.
    provider_deprecated: bool | None = None
    gateway_status: GatewayStatus
    gateway_projection: str | None
    gateway_reason: str | None
    cache_behavior: CacheBehavior
    applicable_auth_modes: tuple[AuthMode, ...]

    def to_detail_dict(self) -> dict[str, Any]:
        gateway: dict[str, Any] = {"status": self.gateway_status}
        if self.gateway_status == "enabled":
            gateway["projection"] = self.gateway_projection
        else:
            gateway["reason"] = self.gateway_reason
        gateway["cache_behavior"] = self.cache_behavior
        # WHY published rather than kept internal: without it a DISABLED row cannot
        # say WHICH credential would enable it, so "not available under this auth
        # mode" is a dead end for the client. Empty tuple == no gateway rule at all.
        # No new exposure: ``context.auth_mode`` already names the reading mode in
        # this same profile-bound document, and these are gateway-authored policy
        # values, never account or credential material.
        gateway["applicable_auth_modes"] = list(self.applicable_auth_modes)
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
                # WHY always present, and null when unknown: a client reading a
                # UNIFORM shape can tell "the provider declares this deprecated"
                # from "nobody said" without a key-presence check. Omitting the key
                # for the silent case makes those two indistinguishable in JSON.
                "deprecated": self.provider_deprecated,
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
    INVARIANT: one provider target == at most one rule per provider rule set, so
    two request paths can never race to write the same wire field. ``rule.target``
    is ``provider_target or request_path``, so direct rules fold into the already
    unique request-path space and only genuine collisions (two native paths → one
    target, or a direct path clashing with a native target) trip this. Without it a
    provider misconfig would surface only as a caller-facing ``duplicate_channel``
    400 in ``_project`` — and only if a caller supplied both channels at once.
    """
    ordered = sorted(rules, key=lambda rule: rule.request_path)
    seen_paths: set[str] = set()
    seen_targets: dict[str, str] = {}
    for rule in ordered:
        if rule.request_path in seen_paths:
            raise DuplicateParameterRuleError(f"duplicate rule for {rule.request_path!r}")
        seen_paths.add(rule.request_path)
        if rule.target in seen_targets:
            raise DuplicateParameterRuleError(
                f"duplicate provider target {rule.target!r} for request paths "
                f"{seen_targets[rule.target]!r} and {rule.request_path!r}"
            )
        seen_targets[rule.target] = rule.request_path
    return tuple(ordered)


def inline_supported_parameters(
    rules: Iterable[ParameterProjectionRule],
    *,
    available_auth_modes: tuple[AuthMode, ...],
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


def overlay_observations(
    base: Iterable[ProviderParameterObservation],
    overlay: Iterable[ProviderParameterObservation],
    *,
    stale: bool = False,
) -> tuple[ProviderParameterObservation, ...]:
    """Merge dynamic evidence over labelled-local evidence, one verdict per path.

    FEATURE: model-specific provider evidence. A provider's reviewed
    labelled-local observations describe its ENDPOINT and cannot vary by model; a
    discovered snapshot describes ONE model. Where both speak, the more specific
    claim decides — so the detailed contract stops reporting the same evidence for
    every model of a provider.

    INVARIANT (evidence axis only): this moves ``support`` / ``source`` / ``stale``
    and may ADD a path the base never knew. It returns observations, never rules —
    so nothing here can enable a parameter, change the ``/v1/models`` summary, or
    authorize dispatch. A path the overlay is SILENT about keeps its base verdict:
    a partial source must never read as a denial.

    INVARIANT (silence is per FIELD, not only per PATH): an observation carries more
    than one axis, and different sources speak on different ones. A per-model catalog
    reports SUPPORT and knows nothing about a field's schema or lifecycle, so letting
    it win wholesale would erase endpoint facts it never contradicted — the same
    "partial source read as a denial" bug, one level down. ``schema`` and
    ``deprecated`` are therefore carried forward when the overlay is silent (``None``)
    about them, while the support axis is replaced outright.

    ``stale`` is the CACHE's verdict about this particular read, so it is stamped
    onto the overlay entries here rather than carried by the parser — and it is set
    in both directions, so a fresh read can never inherit a stale label.
    """
    merged = {observation.request_path: observation for observation in base}
    for observation in overlay:
        prior = merged.get(observation.request_path)
        # model_copy takes FIELD names, never the ``schema`` alias.
        updates: dict[str, Any] = {}
        if observation.stale != stale:
            updates["stale"] = stale
        if prior is not None:
            if observation.parameter_schema is None and prior.parameter_schema is not None:
                updates["parameter_schema"] = prior.parameter_schema
            if observation.deprecated is None and prior.deprecated is not None:
                updates["deprecated"] = prior.deprecated
        merged[observation.request_path] = (
            observation.model_copy(update=updates) if updates else observation
        )
    return tuple(merged[path] for path in sorted(merged))


def overlay_tool_capabilities(
    base: Iterable[ToolCapability],
    overlay: Iterable[ProviderToolObservation],
) -> tuple[ToolCapability, ...]:
    """Apply discovered tool evidence to a provider's reviewed tool capabilities.

    FEATURE: backend-specific tool evidence. A tool type is named in TWO published
    places — the ``tools``/``tool_choice`` request paths and the tools section — so
    a discovered verdict that reached only one of them would make the detailed
    contract contradict itself. This is the tools-section half.

    INVARIANT (evidence axis only): this moves ``provider_support`` and NOTHING
    else. ``gateway_status`` is policy, derived from the provider's reviewed rules,
    so a backend that lacks a tool cannot change what the gateway forwards — nor the
    ``/v1/models`` summary, which filters on ``gateway_status``.

    INVARIANT (restrict-only): a tool type with no base capability is IGNORED, not
    added. This is where tools DIVERGE from parameters: an unruled discovered
    request path becomes a visible DISABLED entry because ``compose_contract_entries``
    derives that status from the rules, but a ``ToolCapability`` carries both axes in
    one record — admitting an unknown type would mean INVENTING a gateway decision
    for a tool the gateway has no rule for. Silence about a known type likewise
    preserves its reviewed verdict: a partial source is not a denial.
    """
    verdicts = {observation.tool_type: observation.support for observation in overlay}
    return tuple(
        tool
        if tool.tool_type not in verdicts
        else tool.model_copy(update={"provider_support": verdicts[tool.tool_type]})
        for tool in base
    )


def supported_tool_types(tools: Iterable[ToolCapability]) -> tuple[str, ...]:
    """Sorted accepted tool-type values whose gateway status is enabled."""
    return tuple(sorted({tool.tool_type for tool in tools if tool.gateway_status == "enabled"}))


def compose_contract_entries(
    rules: Iterable[ParameterProjectionRule],
    observations: Iterable[ProviderParameterObservation],
    *,
    auth_mode: AuthMode,
) -> tuple[ParameterContractEntry, ...]:
    """Overlay provider observations with gateway rules for one auth mode.

    - A rule applicable to ``auth_mode`` produces an ENABLED entry.
    - A rule the gateway HAS but which does not cover ``auth_mode`` produces a
      DISABLED entry with ``projection_not_available_for_auth_mode``, carrying the
      modes that DO cover it.
    - An observed-but-unruled path produces a DISABLED entry with
      ``projection_not_implemented`` — visible, but never dispatchable.

    INVARIANT (OME-649): a rule is never DROPPED for not covering the read's auth
    mode; only its ``gateway.status`` reacts. Filtering it out here would make the
    contract claim the gateway has no projection at all for that path, which is
    both false and unactionable — the client cannot see that switching credentials
    would enable it. Dispatch is unaffected: it filters rules by auth mode on its
    OWN path (``parameter_projection``), and every entry produced here for a
    non-covering mode is DISABLED, so nothing new becomes forwardable.

    INVARIANT: the published ``applicable_auth_modes`` is the rule's real tuple, so
    the contract shows the same value ``_rules_revision`` already hashes. The
    identity digest covers EVERY rule regardless of the read's mode; publishing
    only the covering ones meant hashing a field the document never showed.
    """
    by_path = {rule.request_path: rule for rule in rules}
    observed = {obs.request_path: obs for obs in observations}
    entries: list[ParameterContractEntry] = []
    for path in sorted(set(by_path) | set(observed)):
        rule = by_path.get(path)
        obs = observed.get(path)
        # ``covering`` is the rule that AUTHORIZES this read; ``rule`` is merely the
        # rule that EXISTS. Keeping them as separate names is what lets the three
        # cases below stay one expression each.
        covering = rule if rule is not None and auth_mode in rule.applicable_auth_modes else None
        if rule is None:
            reason = _DISABLED_UNPROJECTED_REASON
        elif covering is None:
            reason = _DISABLED_AUTH_MODE_REASON
        else:
            reason = None
        entries.append(
            ParameterContractEntry(
                request_path=path,
                # The rule's reviewed schema wins wherever one exists — including on
                # a disabled-by-auth row, where it is exactly the validation the
                # client would face after connecting a covering credential.
                schema=(rule.parameter_schema if rule is not None else None)
                or (obs.parameter_schema if obs is not None else None),
                provider_support=obs.support if obs else "unknown",
                provider_source=obs.source if obs else "none",
                provider_stale=obs.stale if obs else False,
                provider_deprecated=obs.deprecated if obs else None,
                gateway_status="enabled" if covering else "disabled",
                gateway_projection=covering.projection_kind if covering else None,
                gateway_reason=reason,
                # A disabled row forwards nothing, so it keys nothing — ``bypass``
                # describes what this read actually does, in every disabled case.
                cache_behavior=covering.cache_behavior if covering else "bypass",
                applicable_auth_modes=rule.applicable_auth_modes if rule else (),
            )
        )
    return tuple(entries)
