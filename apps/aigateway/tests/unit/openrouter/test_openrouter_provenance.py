"""litellm-1.87.0 error-provenance state machine (OME-428 third-review blockers D + F).

# STORY: as the gateway I retry ONLY a proven real transport overload; a
# converter-origin (HTTP-200 body) error or an unprovable/ambiguous error is
# non-retryable and sanitized — so a future litellm shape can never be silently
# retried into an amplified, already-billed upstream call.
# INVARIANT: three explicit outcomes — TRANSPORT (proven wire failure),
# BODY (proven converter-origin), AMBIGUOUS (unprovable -> fail closed ->
# treated as body). ``is_http200_body_error`` is True for BODY and AMBIGUOUS.
"""

from __future__ import annotations

import httpx
import pytest
from litellm.exceptions import APIError

from aigateway.plugins.openrouter_provider.provenance import (
    ErrorProvenance,
    classify_provenance,
    converter_error_status,
    is_http200_body_error,
)


def _exc(message: str = "boom", *, status: object = None) -> Exception:
    exc = Exception(message)
    if status is not None:
        exc.status_code = status  # type: ignore[attr-defined]
    return exc


def _chained(outer: BaseException, cause: BaseException) -> BaseException:
    outer.__cause__ = cause
    return outer


def _converter_exc(context_status: object) -> APIError:
    context = Exception()
    context.status_code = context_status  # type: ignore[attr-defined]
    context.message = "provider body error"  # type: ignore[attr-defined]
    outer = APIError(
        status_code=400,
        message="mapped converter error",
        llm_provider="openrouter",
        model="openrouter/example/model",
    )
    outer.__cause__ = context
    return outer


# --- classify_provenance: the state machine ---


def test_headers_without_httpx_chain_are_ambiguous() -> None:
    exc = _exc()
    exc.litellm_response_headers = {"retry-after": "7"}  # type: ignore[attr-defined]
    assert classify_provenance(exc) is ErrorProvenance.AMBIGUOUS
    assert is_http200_body_error(exc) is True


def test_httpx_error_in_chain_is_transport() -> None:
    wire = httpx.HTTPStatusError(
        "429",
        request=httpx.Request("POST", "https://openrouter.ai/api/v1"),
        response=httpx.Response(429, request=httpx.Request("POST", "https://openrouter.ai/api/v1")),
    )
    exc = _chained(_exc(), wire)
    assert classify_provenance(exc) is ErrorProvenance.TRANSPORT
    assert is_http200_body_error(exc) is False


def test_bare_exception_cause_is_body() -> None:
    # litellm's converter raises `from` a bare (non-httpx) Exception.
    exc = _converter_exc(429)
    assert classify_provenance(exc) is ErrorProvenance.BODY
    assert is_http200_body_error(exc) is True


def test_no_chain_is_ambiguous_and_non_retryable() -> None:
    # No wire headers, no cause chain: unprovable -> fail closed (blocker F).
    exc = _exc()
    assert classify_provenance(exc) is ErrorProvenance.AMBIGUOUS
    assert is_http200_body_error(exc) is True


def test_cyclic_chain_terminates_and_is_non_retryable() -> None:
    a = _exc("a")
    b = _exc("b")
    a.__cause__ = b
    b.__cause__ = a  # cycle: the walker must not hang
    assert classify_provenance(a) is ErrorProvenance.AMBIGUOUS
    assert is_http200_body_error(a) is True


def test_headers_do_not_override_exact_converter_shape() -> None:
    exc = _converter_exc(429)
    exc.litellm_response_headers = {"retry-after": "1"}  # type: ignore[attr-defined]
    assert classify_provenance(exc) is ErrorProvenance.BODY


def test_arbitrary_non_httpx_chain_is_ambiguous_and_status_is_not_trusted() -> None:
    exc = _chained(RuntimeError("outer"), _exc("unrelated", status=401))
    assert classify_provenance(exc) is ErrorProvenance.AMBIGUOUS
    assert converter_error_status(exc) is None


# --- converter_error_status: context status + 422 fold (blocker D) ---


@pytest.mark.parametrize(
    ("context_status", "expected"),
    [
        (400, 400),
        (402, 402),
        (429, 429),
        (500, 500),
        (503, 503),
        (422, None),  # litellm "no derivable status" sentinel -> None -> 502
        ("429", None),  # string is rejected by the strict validator
        ("²", None),  # Unicode-digit hazard: never crashes
        (None, None),
    ],
)
def test_converter_error_status_reads_context_and_folds_422(
    context_status: object, expected: int | None
) -> None:
    exc = _converter_exc(context_status)
    assert converter_error_status(exc) == expected


def test_converter_error_status_without_chain_is_none() -> None:
    # An ambiguous error has no derivable status -> None -> caller renders 502.
    assert converter_error_status(_exc()) is None
