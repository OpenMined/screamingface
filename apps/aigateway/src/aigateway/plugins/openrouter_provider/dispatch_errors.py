"""Sanitized gateway errors raised on the OpenRouter dispatch path.

INVARIANT: gateway-authored text only. No raw provider message, metadata or
caller value reaches a client through these — an upstream failure is reported as
a status plus a gateway code, and nothing else.

WHY separate from ``response_errors``: that module DETECTS an error inside a
provider payload; this one CONSTRUCTS the gateway's answer to one. Keeping them
apart is what stops a detector from quietly gaining the power to shape the
client-facing error.
"""

from __future__ import annotations

from fastapi import HTTPException

from aigateway.core.provider_errors import NonRetryableProviderError


def _invalid_model_error() -> HTTPException:
    # Gateway-authored message only — never echo the raw caller value.
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_model",
            "provider": "openrouter",
            "message": (
                "model must be 'openrouter/<author>/<model>' with an optional single ':variant'"
            ),
        },
    )


class _UnsafeLiteLLMStateError(HTTPException):
    """A pre-dispatch global-state conflict that the retry loop must not repeat."""

    aigw_non_retryable = True


def _unsafe_litellm_state_error() -> _UnsafeLiteLLMStateError:
    return _UnsafeLiteLLMStateError(
        status_code=503,
        detail={
            "code": "provider_unavailable",
            "message": "OpenRouter dispatch is unavailable",
        },
    )


class _UnexpectedRoutingPolicyError(HTTPException):
    """A projected ``provider`` policy the gateway did not build. Never retried."""

    aigw_non_retryable = True


def _unexpected_routing_policy_error() -> _UnexpectedRoutingPolicyError:
    """OME-704: the provider boundary could not reconstruct a routing policy.

    INVARIANT: takes NO arguments. There is nothing a caller value or a projected
    key could add to this response that would not be a leak — the whole reason it
    exists is that the gateway found something it does not recognize, and naming
    that something would describe internal projection state to a client.

    Deliberately INDISTINGUISHABLE from ``_unsafe_litellm_state_error``: both are
    "the gateway will not dispatch this", and a client that could tell them apart
    could probe which internal guard it tripped. It is non-retryable because the
    mismatch is deterministic — the same request rebuilt the same way fails again.
    """
    return _UnexpectedRoutingPolicyError(
        status_code=503,
        detail={
            "code": "provider_unavailable",
            "message": "OpenRouter dispatch is unavailable",
        },
    )


def _embedded_error_exception(status: int | None) -> HTTPException:
    """Sanitized gateway error for an embedded provider failure.

    Only the numeric status survives; raw provider message/metadata is
    discarded. Malformed/status-less embedded errors map to 502 (D9).

    # INVARIANT (CODE-2): the upstream call already returned this payload, so
    # the error is non-retryable — an embedded 429/503/529 must make exactly
    # one upstream call. No Retry-After is invented: the embedded JSON schema
    # was not shown to carry one; validated hints survive only on actual
    # transport exceptions.
    """
    resolved = status if status is not None else 502
    code = "provider_error"
    if resolved == 401:
        code = "auth_required"
    elif resolved == 400:
        code = "bad_request"
    elif resolved == 429:
        code = "rate_limited"
    elif resolved >= 500 and status is not None:
        code = "provider_unavailable"
    return NonRetryableProviderError(
        status_code=resolved,
        detail={"code": code, "message": "OpenRouter reported a provider error"},
    )
