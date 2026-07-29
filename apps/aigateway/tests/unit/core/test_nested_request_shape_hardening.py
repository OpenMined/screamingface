"""Regression coverage for nested OpenAI-compatible request shapes."""

from __future__ import annotations

import pytest

from aigateway.core.request_hardening import chat_body_shape_error


@pytest.mark.parametrize(
    "tools",
    [
        [{"type": "function"}],
        [{"type": "function", "function": {}}],
        [{"type": "function", "function": {"name": ""}}],
    ],
)
def test_function_tools_require_a_non_empty_name(tools: list[dict[str, object]]) -> None:
    error = chat_body_shape_error(
        {
            "model": "gemini/gemini-2.5-pro",
            "messages": [],
            "tools": tools,
        }
    )

    assert error == "each function tool must include a non-empty function.name"


@pytest.mark.parametrize(
    "response_format",
    [
        {"type": "json_schema"},
        {"type": "json_schema", "json_schema": {}},
        {"type": "json_schema", "json_schema": {"schema": "not-an-object"}},
    ],
)
def test_json_schema_response_format_requires_a_schema_object(
    response_format: dict[str, object],
) -> None:
    error = chat_body_shape_error(
        {
            "model": "ollama/llama3.2",
            "messages": [],
            "response_format": response_format,
        }
    )

    assert error == "response_format.json_schema.schema must be an object"


def test_complete_nested_parameter_shapes_are_accepted() -> None:
    error = chat_body_shape_error(
        {
            "model": "gemini/gemini-2.5-pro",
            "messages": [],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "weather", "parameters": {"type": "object"}},
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"schema": {"type": "object"}},
            },
        }
    )

    assert error is None
