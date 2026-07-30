"""OpenRouter price + privacy routing policy (OME-704).

FEATURE: four reviewed routing controls — cheapest-first ordering, a prompt-token
price ceiling, a completion-token price ceiling, and a downstream data policy —
exposed to the caller as five leaves under the ``provider_params`` wrapper and
projected onto OpenRouter's ``provider`` object.

INVARIANT: this module is the ONE place the four controls are written down. The
rules (``parameters.py``), the evidence labels (``observations.py``) and the wire
reconstruction all derive from ``ROUTING_CONTROLS``, so a fifth control cannot be
half-added: a leaf that is not in this table has no rule, no observation and no
wire location.

INVARIANT: raw ``provider`` is never a caller request path. The upstream object is
RECONSTRUCTED by the gateway from this allowlist, which is why the excluded
members of that object (``order``, ``only``, ``ignore``, ``allow_fallbacks``,
``quantizations``, ``require_parameters``) cannot be reached from any accepted
value — there is no code path that copies a caller-supplied ``provider`` field.

WHY prices are STRINGS, not JSON numbers: a price ceiling is only useful if it is
the number the caller wrote. JSON numbers are binary floating point, so
``0.0000001`` becomes a nearby binary value during PARSING — before any schema
could inspect it — and the gateway would enforce a ceiling the caller never
chose. A decimal string crosses the boundary exactly, and the pattern below is
what makes it a number the gateway can reason about.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from typing import Any, NamedTuple

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ParameterValidationError,
)
from aigateway.core.parameter_projection import WRAPPER_KEY
from aigateway.core.profile_models import AuthMode
from aigateway.core.standard_parameters import provider_native_rule

from .dispatch_errors import _unexpected_routing_policy_error

# The upstream object every control projects into. Named once: the reconstruction
# and the rule targets must agree, and a typo in either would silently produce an
# unexpected projected policy (which the boundary then refuses to guess about).
PROVIDER_OBJECT = "provider"

# ACCEPTED PRICE GRAMMAR: a non-negative fixed-point decimal, no exponent, no
# sign, no leading zero, no whitespace. Anchored because the schema is PUBLISHED —
# a JSON-Schema consumer applies partial-match semantics, so an unanchored pattern
# would promise clients something looser than the gateway enforces.
#
# WHY each exclusion is deliberate:
#   - exponents ("1e5") are a second spelling of one value, and `Decimal` would
#     accept them while OpenRouter's documented form is fixed-point;
#   - a leading "+" or "-" makes a ceiling that is not a ceiling, or a second
#     spelling of a positive one;
#   - "01" is an ambiguous spelling; ".5" / "1." are incomplete;
#   - "NaN" / "inf" are `Decimal`-parseable and are NOT prices;
#   - whitespace is invisible in a diff and in a log.
PRICE_PATTERN = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"

# WHY a length bound at all: the pattern alone admits an arbitrarily long digit
# run, and the boundary later parses the value as a `Decimal` to normalize it. 64
# characters is far more precision than any per-token price needs and bounds both
# the regex engine and the parse. Checked BEFORE the pattern (see ParameterSchema).
PRICE_MAX_LENGTH = 64

# `price` is the ONLY exposed sort. Ordering by throughput or latency is provider
# SELECTION policy, which this task excludes and OME-703 owns; exposing it here
# would let a caller steer traffic to a chosen endpoint through the price door.
SORT_SCHEMA = ParameterSchema(type="string", enum=("price",))
PRICE_SCHEMA = ParameterSchema(type="string", pattern=PRICE_PATTERN, max_length=PRICE_MAX_LENGTH)
DATA_COLLECTION_SCHEMA = ParameterSchema(type="string", enum=("allow", "deny"))
ZDR_SCHEMA = ParameterSchema(type="boolean")


def normalize_price(value: str) -> str:
    """Canonicalize a validated price string EXACTLY.

    One value must have exactly one wire spelling, so a future cache key over the
    resolved routing policy (OME-702) cannot read ``"1.000"`` and ``"1"`` as two
    different policies.

    WHY ``format(Decimal(v), "f")`` and not ``Decimal.normalize()``:
    ``normalize()`` is a CONTEXT operation bounded by the decimal context's
    precision (28 significant digits by default), so it would silently ROUND a
    64-character ceiling — and it renders ``100`` as ``"1E+2"``, an exponent
    spelling OpenRouter's documented decimal form does not use. ``format(…, "f")``
    is exact at any length and never exponential.

    WHY the trailing-zero strip is CONDITIONAL on a decimal point: an
    unconditional ``rstrip("0")`` would turn ``"10"`` into ``"1"`` — a tenfold
    change to a price the caller set.

    INVARIANT (precondition): the value has already matched ``PRICE_PATTERN``, so
    ``Decimal`` cannot fail here. The only caller validates immediately before.
    """
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class RoutingControl(NamedTuple):
    """One caller leaf, its upstream location, and the schema that admits it."""

    leaf: str
    target_path: tuple[str, ...]
    schema: ParameterSchema
    # Canonicalizes an admitted value on its way to the wire. Table-driven rather
    # than inferred from the schema, so "which values get rewritten" is readable
    # in one place instead of hidden behind a type check.
    normalizer: Callable[[Any], Any] | None = None
    # ``false`` and absence mean the same thing upstream, so the honest encoding of
    # "I have no constraint" is to send nothing. Only meaningful for booleans.
    omit_if_false: bool = False

    @property
    def request_path(self) -> str:
        return f"{WRAPPER_KEY}.{self.leaf}"

    @property
    def provider_target(self) -> str:
        return ".".join((PROVIDER_OBJECT, *self.target_path))


# AIDEV-NOTE: the reviewed surface. Adding a control means adding a row HERE (with
# its reviewed schema) — the rules, the observations and the reconstruction all
# follow. Removing a row removes the control everywhere, including the published
# contract. Every row needs the same review as a new provider capability: it widens
# what a caller may say about routing.
ROUTING_CONTROLS: tuple[RoutingControl, ...] = (
    # `sort: "price"` asks OpenRouter to prefer the cheapest eligible endpoint. It
    # is an ORDERING preference, not a guarantee, and not a spend limit.
    RoutingControl("sort", ("sort",), SORT_SCHEMA),
    # UNIT-RATE ceilings (USD per million tokens as OpenRouter documents them), not
    # a request budget and not a run budget: they filter which endpoints are
    # eligible by their advertised rate. A long request at an allowed rate can
    # still cost more than a short one at a higher rate.
    RoutingControl(
        "max_price_prompt", ("max_price", "prompt"), PRICE_SCHEMA, normalizer=normalize_price
    ),
    RoutingControl(
        "max_price_completion",
        ("max_price", "completion"),
        PRICE_SCHEMA,
        normalizer=normalize_price,
    ),
    # `deny` filters endpoints by OpenRouter's data-collection/training
    # classification. It is an ELIGIBILITY filter, NOT a retention guarantee: it
    # says nothing about what AIGateway, URL4, logs, tools or caches retain.
    RoutingControl("data_collection", ("data_collection",), DATA_COLLECTION_SCHEMA),
    # `zdr: true` restricts routing to endpoints OpenRouter marks zero-data-
    # retention. Upstream endpoint ELIGIBILITY only — same caveat as above, and it
    # makes no claim about anything on this side of the boundary.
    RoutingControl("zdr", ("zdr",), ZDR_SCHEMA, omit_if_false=True),
)

ROUTING_CONTROL_LEAVES: frozenset[str] = frozenset(control.leaf for control in ROUTING_CONTROLS)


def routing_policy_rules(
    *, auth_modes: tuple[AuthMode, ...], projection_revision: str
) -> tuple[ParameterProjectionRule, ...]:
    """The five wrapped-native rules for the reviewed routing controls.

    INVARIANT: ``cache_behavior="bypass"`` on every one, stated explicitly rather
    than inherited. The response a caller gets depends on WHICH endpoint served
    it, and the chosen endpoint is a function of the whole resolved routing
    policy. Until the cache key can carry that policy (OME-702), a cached answer
    produced under a different ceiling or data policy would otherwise be served as
    though it satisfied this request's constraints — a correctness bug for price
    and a privacy bug for data policy.
    """
    return tuple(
        provider_native_rule(
            control.request_path,
            provider_target=control.provider_target,
            auth_modes=auth_modes,
            schema=control.schema,
            projection_revision=projection_revision,
            cache_behavior="bypass",
            output_affecting=True,
        )
        for control in ROUTING_CONTROLS
    )


# --- reconstruction: the gateway builds the upstream object -------------------

# The gateway-owned strict-routing policy (OME-651), forced on EVERY chat dispatch.
#
# WHY: OpenRouter defaults `provider.require_parameters` to false and documents that
# an endpoint which does not support a supplied parameter may still receive the
# request and ignore the unknown field. Without this, gateway acceptance, a published
# `enabled` status and a successful projection can all hold while the parameter has no
# effect — HTTP 200, silently wrong. Per-model evidence cannot close the gap: one
# OpenRouter model is served by several endpoints with different parameter support, so
# only the provider knows which one can honor this request.
#
# INVARIANT: a successful OpenRouter completion means the selected endpoint declared
# support for EVERY supplied parameter. The alternative is an explicit provider
# refusal, never a silent discard. That now covers the OME-704 routing controls too: a
# price ceiling or data policy the endpoint cannot honor must fail, not be dropped.
#
# AIDEV-NOTE: this is policy, NOT a projected caller parameter — which is why
# reconstruction writes it unconditionally and treats an incoming value as irrelevant
# rather than "unexpected". On the wire it rides the same path as the projected
# controls: litellm folds a non-OpenAI dispatch kwarg into `extra_body`, then the
# OpenRouter transform flattens `extra_body` onto the top level. That double
# indirection is a litellm behaviour, not a promise, so `test_openrouter_strict_routing`
# and `test_openrouter_routing_policy_wire` pin the FINAL wire JSON against the
# installed version — if it ever changes, strictness would vanish silently.
STRICT_ROUTING_KEY = "require_parameters"
_GATEWAY_OWNED_KEYS: frozenset[str] = frozenset({STRICT_ROUTING_KEY})

# Every writable wire location, keyed by its path inside the `provider` object.
_BY_TARGET: dict[tuple[str, ...], RoutingControl] = {
    control.target_path: control for control in ROUTING_CONTROLS
}
# Locations that are OBJECTS rather than leaves (currently just `max_price`).
_CONTAINER_KEYS: frozenset[str] = frozenset(
    control.target_path[0] for control in ROUTING_CONTROLS if len(control.target_path) == 2
)


def build_provider_policy(projected: Any) -> dict[str, Any]:
    """Build the upstream ``provider`` object from a projected routing policy.

    INVARIANT: RECONSTRUCTION, never a merge or a filter. Every value written here
    is written to a location named in ``ROUTING_CONTROLS``, so there is no code
    path that can carry an unrecognized ``provider`` member to OpenRouter. That is
    what keeps the excluded control plane (``order``, ``only``, ``ignore``,
    ``allow_fallbacks``, ``quantizations``) unreachable — not a denylist, which
    would have to be kept in step with whatever OpenRouter adds next.

    INVARIANT: an unexpected key or shape is REFUSED, not dropped. Dropping it
    would be the worse failure: the gateway told the caller it accepted a price
    ceiling or a data policy, and the request would then be served without it.
    Refusing is also the only honest answer to "the gateway does not understand its
    own projected state" — see ``_unexpected_routing_policy_error`` for why the
    response says nothing about what was found.

    INVARIANT: values are RE-VALIDATED here against the same schemas admission
    used. The classifier has already validated them, and that redundancy is the
    point: the two layers are deliberately independent, so a projection bug cannot
    put an unvalidated price on the wire just because admission was bypassed.

    A fresh dict per call: a shared object would let one request's mutation become
    the next request's policy.
    """
    policy: dict[str, Any] = {}
    for target_path, value in _projected_leaves(projected):
        control = _BY_TARGET.get(target_path)
        if control is None:
            raise _unexpected_routing_policy_error()
        _place(policy, control, value)
    policy[STRICT_ROUTING_KEY] = True
    return policy


def _projected_leaves(projected: Any) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Flatten a projected ``provider`` object into (target path, value) pairs.

    Descends exactly one level, and only into a declared container: nothing else
    in the allowlist is nested, so a deeper structure is by definition not
    something reconstruction can place.
    """
    if projected is None:
        return
    if not isinstance(projected, Mapping):
        raise _unexpected_routing_policy_error()
    for key, value in projected.items():
        if key in _GATEWAY_OWNED_KEYS:
            continue
        if key in _CONTAINER_KEYS:
            if not isinstance(value, Mapping):
                raise _unexpected_routing_policy_error()
            for nested_key, nested_value in value.items():
                yield (key, nested_key), nested_value
            continue
        yield (key,), value


def _place(policy: dict[str, Any], control: RoutingControl, value: Any) -> None:
    try:
        control.schema.validate_value(value)
    except ParameterValidationError:
        # `from None`: the chain is dropped deliberately. The client-facing response
        # is fixed text, and suppressing the cause keeps a schema message — now or
        # after a future edit — from carrying a caller value into a traceback or log.
        raise _unexpected_routing_policy_error() from None
    if control.omit_if_false and value is False:
        return
    if control.normalizer is not None:
        value = control.normalizer(value)
    node = policy
    for segment in control.target_path[:-1]:
        node = node.setdefault(segment, {})
    node[control.target_path[-1]] = value
