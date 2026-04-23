"""Unit tests for the collection parser (JSON, JSONL, CSV)."""

from __future__ import annotations

from screamingface.plugins.url4_executor.collection_parser import parse_collection


class TestJsonArray:
    def test_simple_string_array(self):
        assert parse_collection('["a", "b", "c"]') == ["a", "b", "c"]

    def test_object_array(self):
        result = parse_collection('[{"name":"alice"},{"name":"bob"}]')
        assert len(result) == 2
        assert '"alice"' in result[0]
        assert '"bob"' in result[1]

    def test_mixed_types(self):
        result = parse_collection('[1, "two", true, null]')
        assert result == ["1", "two", "true", "null"]

    def test_empty_array(self):
        assert parse_collection("[]") == []


class TestJsonl:
    def test_object_per_line(self):
        body = '{"q":"What is 2+2?"}\n{"q":"Capital of France?"}\n{"q":"Color of sky?"}'
        result = parse_collection(body)
        assert len(result) == 3
        assert "2+2" in result[0]
        assert "France" in result[1]

    def test_string_per_line(self):
        body = '"hello"\n"world"\n"test"'
        result = parse_collection(body)
        assert result == ["hello", "world", "test"]

    def test_blank_lines_skipped(self):
        body = '{"a":1}\n\n{"b":2}\n'
        result = parse_collection(body)
        assert len(result) == 2


class TestCsv:
    def test_basic_csv(self):
        body = "name,age\nalice,30\nbob,25"
        result = parse_collection(body)
        assert len(result) == 2
        # Each row is a JSON object string
        import json

        row1 = json.loads(result[0])
        assert row1["name"] == "alice"
        assert row1["age"] == "30"


class TestFallback:
    def test_plain_text_lines(self):
        body = "line one\nline two\nline three"
        result = parse_collection(body)
        assert result == ["line one", "line two", "line three"]

    def test_empty_body(self):
        assert parse_collection("") == []
        assert parse_collection("   ") == []
