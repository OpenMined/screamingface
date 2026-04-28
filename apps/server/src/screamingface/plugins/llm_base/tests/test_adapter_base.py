"""Unit tests for the shared adapter_base helpers (SF-110/SF-123/SF-124)."""

from __future__ import annotations

from screamingface.plugins.llm_base.adapter_base import (
    collect_provider_metadata,
    extract_system_text,
    parts_to_text,
    serialize_tool_output,
)
from screamingface.plugins.llm_base.messages import TextPart

# ---------------------------------------------------------------------------
# extract_system_text
# ---------------------------------------------------------------------------


def test_extract_system_text_string_passthrough() -> None:
    assert extract_system_text("hello") == "hello"


def test_extract_system_text_none_inputs_return_none() -> None:
    assert extract_system_text(None) is None
    assert extract_system_text("") is None
    assert extract_system_text([]) is None


def test_extract_system_text_concatenates_textparts() -> None:
    parts = [TextPart(text="a"), TextPart(text="b")]
    assert extract_system_text(parts) == "a\n\nb"


def test_extract_system_text_handles_dict_blocks() -> None:
    blocks = [{"text": "x"}, {"text": "y"}]
    assert extract_system_text(blocks) == "x\n\ny"


def test_extract_system_text_mixed_inputs() -> None:
    blocks = [{"text": "x"}, TextPart(text="y"), "z"]
    assert extract_system_text(blocks) == "x\n\ny\n\nz"


# ---------------------------------------------------------------------------
# parts_to_text
# ---------------------------------------------------------------------------


def test_parts_to_text_default_no_separator() -> None:
    parts = [TextPart(text="ab"), TextPart(text="cd")]
    assert parts_to_text(parts) == "abcd"


def test_parts_to_text_custom_separator() -> None:
    assert parts_to_text([TextPart(text="a"), TextPart(text="b")], separator=" | ") == "a | b"


def test_parts_to_text_empty_input() -> None:
    assert parts_to_text([]) == ""
    assert parts_to_text(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# serialize_tool_output
# ---------------------------------------------------------------------------


def test_serialize_tool_output_string_passthrough() -> None:
    assert serialize_tool_output("plain text") == "plain text"


def test_serialize_tool_output_dict_jsondumps() -> None:
    assert serialize_tool_output({"k": 1}) == '{"k": 1}'


def test_serialize_tool_output_list_jsondumps() -> None:
    assert serialize_tool_output([1, "two"]) == '[1, "two"]'


# ---------------------------------------------------------------------------
# collect_provider_metadata
# ---------------------------------------------------------------------------


def test_collect_provider_metadata_basic() -> None:
    out = collect_provider_metadata({"a": 1, "b": 2, "c": 3}, ("a", "c"), prefix="x")
    assert out == {"x.a": 1, "x.c": 3}


def test_collect_provider_metadata_skips_missing_keys() -> None:
    assert collect_provider_metadata({"a": 1}, ("a", "missing"), prefix="x") == {"x.a": 1}


def test_collect_provider_metadata_includes_none_by_default() -> None:
    assert collect_provider_metadata({"a": None}, ("a",), prefix="x") == {"x.a": None}


def test_collect_provider_metadata_skip_none_drops_explicit_none() -> None:
    out = collect_provider_metadata({"a": None, "b": 2}, ("a", "b"), prefix="x", skip_none=True)
    assert out == {"x.b": 2}
