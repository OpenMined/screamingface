"""OME-305 — OpenRouter's pure projection of what it will send, for the global cache.

FEATURE: one globally shared exact-request cache. Under v1 an OpenRouter request
could never be cached, because ``prepare_chat_body`` rewrites the body and an
inspected rewrite is indistinguishable from an unreviewed one. Here the preparation
is PROJECTED instead, so a bare request becomes cacheable and a routing-controlled
one is keyed by the policy that will actually be sent.

AIDEV-NOTE: this lives OUTSIDE ``plugin.py`` for a reason worth keeping. The
projection must be pure — no I/O, no clock, no credential, no identity — while
``plugin.py`` is where every impure thing this provider does is wired. Separate
modules make that boundary visible to a reader and mean the purity sweep in
``tests/unit/test_global_cache_projection_purity.py`` is checking a file that
contains nothing else. (It also keeps ``plugin.py`` under the 450-line limit, which
is what forced the split, but the homing is the reason to keep it.)
"""

from __future__ import annotations

from typing import Any

from aigateway.core.cache_ports import PROJECTION_BYPASS_REASON, CacheBypass
from aigateway.core.parameter_projection import WRAPPER_KEY

from .dispatch_errors import _UnexpectedRoutingPolicyError
from .routing_policy import PROVIDER_OBJECT, build_provider_policy, project_routing_controls
from .settings import GATEWAY_MODEL_PREFIX, OFFICIAL_API_BASE, is_valid_upstream_model_id

# OME-305: the revision of THIS plugin's output-affecting preparation, as reported
# by ``global_cache_projection``.
#
# INVARIANT: bump it whenever ``prepare_chat_body`` or the projection changes what
# reaches OpenRouter for an unchanged request — a new pinned base, a different
# model-identity rule, a change to how the routing policy is reconstructed. Every
# stored global entry for this provider is then abandoned instead of being re-served
# under semantics it was not produced with.
#
# WHY it is separate from the RULES revision in ``parameters.py``: that one versions
# what a caller may say and where each value lands; this one versions what the
# boundary adds on its own. A change to either must invalidate, and collapsing them
# into one constant would make every rule edit look like a dispatch change.
GLOBAL_CACHE_ADAPTER_REVISION = "openrouter-global-cache-2026-08"


def project_global_cache_request(body: dict[str, Any]) -> dict[str, Any] | CacheBypass:
    """What this provider will send, as a deterministic function of the body.

    The two output-affecting things this boundary adds are the pinned API base and
    the reconstructed routing policy; both are projected here.

    INVARIANT: pure. No I/O, no clock, no randomness, no credential, no identity —
    it receives the request body alone and returns the same answer every time.
    Attribution headers and the injected key are TRANSPORT and stay out.

    INVARIANT: ``resolved_model`` is the UPSTREAM id. The gateway prefix is LiteLLM's
    provider prefix and is stripped exactly once at the wire (D8), so the upstream
    remainder is what OpenRouter actually resolves — and an id this plugin would
    refuse to dispatch yields a bypass here rather than a raise, because a projection
    may never fail a request.

    INVARIANT (ledger decision 12): reconstruction failure is a projection-time
    BYPASS. ``build_provider_policy`` refuses a policy it cannot rebuild, and that
    refusal is a 503 on dispatch; moving the cache read ahead of
    ``prepare_chat_body`` must not turn such a request into a 200 hit. Calling the
    real reconstruction here is also what pins the price and ``zdr`` equivalences:
    two spellings of one ceiling, and a ``false`` flag that is sent as nothing at
    all, canonicalize to one policy and therefore to one key.

    AIDEV-NOTE: the bypass above is proven by a tripwire that was OBSERVED TO FIRE —
    with the ``except`` clause replaced by ``policy = {}``,
    ``test_a_body_whose_routing_policy_cannot_be_rebuilt_is_never_served_from_cache``
    fails with a real key hash in the store's read log. That is the wrong-hit class
    this guard closes: an unrebuildable policy would key as if no policy were asked
    for, so a request demanding a price ceiling would collide with one demanding
    none. Do not replace this bypass with a fallback policy value.
    """
    model = body.get("model")
    if not isinstance(model, str) or not model.startswith(GATEWAY_MODEL_PREFIX):
        return CacheBypass(reason=PROJECTION_BYPASS_REASON)
    upstream = model[len(GATEWAY_MODEL_PREFIX) :]
    if not is_valid_upstream_model_id(upstream):
        return CacheBypass(reason=PROJECTION_BYPASS_REASON)
    try:
        policy = build_provider_policy(project_routing_controls(body.get(WRAPPER_KEY)))
    except _UnexpectedRoutingPolicyError:
        return CacheBypass(reason=PROJECTION_BYPASS_REASON)
    return {
        "resolved_model": upstream,
        "provider_adapter_revision": GLOBAL_CACHE_ADAPTER_REVISION,
        "prepared": {"api_base": OFFICIAL_API_BASE, PROVIDER_OBJECT: policy},
    }
