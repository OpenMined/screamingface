"""Pinning contract: the CODE-1 gate supersets litellm's top-level error guard.

Drives litellm's REAL converter (``convert_to_model_response_object``,
convert_dict_to_response.py:488-525 in 1.87.0) so an upgrade that changes the
benign-shape guard (:491-509) fails loudly here instead of silently shifting
which payloads reach the plugin's top-level scan.

One-way implication: every top-level ``error`` shape the converter raises on
must fire ``_top_level_error_is_meaningful``; the benign trio the converter
passes through must stay silent. The gate is deliberately a SUPERSET —
status-keyed shapes litellm passes (``{"status": 429}``) still fire, so an
embedded status can never render as a 200 success.
"""

from __future__ import annotations

from typing import Any

import pytest
from litellm.litellm_core_utils.llm_response_utils.convert_dict_to_response import (
    convert_to_model_response_object,
)
from litellm.types.utils import ModelResponse

from aigateway.plugins.openrouter_provider.plugin import _top_level_error_is_meaningful


def _payload_with(error: Any) -> dict[str, Any]:
    return {
        "id": "gen-contract",
        "created": 1,
        "model": "anthropic/claude-fable-5",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "error": error,
    }


def _converter_raises(payload: dict[str, Any]) -> bool:
    try:
        convert_to_model_response_object(
            response_object=payload,
            model_response_object=ModelResponse(),
            response_type="completion",
            stream=False,
        )
    except Exception:  # noqa: BLE001 — litellm raises a bare Exception here by design
        return True
    return False


# Shapes litellm's guard raises on (meaningful): the gate MUST fire on all.
_MEANINGFUL = [
    {"message": "boom"},
    {"message": {"nested": "detail"}},
    {"code": 429},
    {"code": 402, "message": "Insufficient credits"},
    {"code": "not-a-status", "message": "boom"},
    "opaque failure string",
    123,  # non-dict/non-str → litellm raises unconditionally …
    0,  # … even when falsy — which is why the gate must not use bool(error)
]

# The benign trio litellm deliberately passes through (:491-509).
_BENIGN = [
    {},
    "",
    {"code": None, "message": ""},
]

# Superset cases: litellm passes them, but the gate still fires so a
# status-keyed error can never masquerade as success.
_STATUS_KEYED = [
    {"status": 429},
    {"status_code": 503},
]


@pytest.mark.parametrize("error", _MEANINGFUL)
def test_gate_fires_on_everything_litellm_raises_on(error: Any) -> None:
    assert _converter_raises(_payload_with(error)) is True
    assert _top_level_error_is_meaningful(error) is True


@pytest.mark.parametrize("error", _BENIGN)
def test_benign_trio_passes_litellm_and_stays_silent(error: Any) -> None:
    assert _converter_raises(_payload_with(error)) is False
    assert _top_level_error_is_meaningful(error) is False


@pytest.mark.parametrize("error", _STATUS_KEYED)
def test_status_keyed_shapes_fire_the_gate_despite_litellm_passing(error: Any) -> None:
    assert _converter_raises(_payload_with(error)) is False
    assert _top_level_error_is_meaningful(error) is True


def test_none_error_is_not_meaningful() -> None:
    assert _top_level_error_is_meaningful(None) is False
