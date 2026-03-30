"""Tests for session-specific model design choices (not Pydantic basics)."""

from __future__ import annotations

from pydantic import BaseModel

from screamingface.core.session import SessionMetadata


class TestSessionMetadataGeneric:
    def test_base_fields(self) -> None:
        meta = SessionMetadata()
        assert meta.id
        assert meta.provider == ""
        assert meta.message_count == 0
        assert meta.tags == []
        assert meta.data is None

    def test_provider_specific_data(self) -> None:
        class MyData(BaseModel):
            custom_field: str = "hello"

        meta = SessionMetadata(provider="test", data=MyData())
        assert meta.data is not None
        assert meta.data.custom_field == "hello"

    def test_extra_fields_round_trip(self) -> None:
        raw = {
            "provider": "anthropic",
            "title": "test",
            "unknown_field": "preserved",
        }
        meta = SessionMetadata.model_validate(raw)
        dumped = meta.model_dump()
        assert dumped["unknown_field"] == "preserved"

    def test_json_round_trip_with_data(self) -> None:
        meta = SessionMetadata(provider="anthropic", title="chat", tags=["dev"])
        json_str = meta.model_dump_json()
        restored = SessionMetadata.model_validate_json(json_str)
        assert restored.id == meta.id
        assert restored.provider == "anthropic"
        assert restored.tags == ["dev"]
