from __future__ import annotations

import pytest

from aigateway.plugins.openrouter_provider.response_errors import (
    find_converted_error,
    find_raw_error,
)


@pytest.mark.parametrize("value", [None, {}, "", {"code": None, "message": ""}])
def test_benign_top_level_error_is_not_a_failure(value: object) -> None:
    assert find_raw_error({"error": value}).found is False
    assert find_converted_error({"error": value}).found is False


def test_raw_error_extracts_status_and_allowlisted_type() -> None:
    error = find_raw_error(
        {
            "error": {
                "code": 429,
                "message": "must not survive",
                "metadata": {
                    "error_type": "rate_limit_exceeded",
                    "provider_code": "must-not-survive",
                },
            }
        }
    )

    assert error.found is True
    assert error.status == 429
    assert error.error_type == "rate_limit_exceeded"
    assert "must" not in repr(error)


def test_raw_error_detects_choice_error_and_finish_reason() -> None:
    with_error = find_raw_error(
        {"choices": [{"error": {"code": 402, "metadata": {"error_type": "payment_required"}}}]}
    )
    finish_only = find_raw_error({"choices": [{"finish_reason": "error"}]})

    assert (with_error.found, with_error.status, with_error.error_type) == (
        True,
        402,
        "payment_required",
    )
    assert (finish_only.found, finish_only.status, finish_only.error_type) == (True, None, None)


def test_converted_error_preserves_litellm_specific_fields() -> None:
    converted = find_converted_error(
        {
            "choices": [
                {
                    "message": {
                        "provider_specific_fields": {
                            "error": {"code": 503},
                            "native_finish_reason": "error",
                        }
                    }
                }
            ]
        }
    )

    assert (converted.found, converted.status) == (True, 503)


def test_raw_error_ignores_litellm_only_fields() -> None:
    raw = find_raw_error(
        {
            "choices": [
                {
                    "message": {
                        "provider_specific_fields": {
                            "error": {"code": 503},
                            "native_finish_reason": "error",
                        }
                    }
                }
            ]
        }
    )

    assert raw.found is False


def test_raw_error_does_not_merge_evidence_from_separate_errors() -> None:
    raw = find_raw_error(
        {
            "error": {"code": 503},
            "choices": [{"error": {"metadata": {"error_type": "permission_denied"}}}],
        }
    )

    assert raw.status == 503
    assert raw.error_type is None


@pytest.mark.parametrize("code", [True, 399, 600, 429.0, "429", "４２９"])
def test_embedded_status_must_be_a_strict_http_error(code: object) -> None:
    error = find_raw_error({"error": {"code": code}})

    assert error.found is True
    assert error.status is None
