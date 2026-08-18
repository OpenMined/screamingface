"""DRACO scalar records reject Python coercions that are not valid JSON field encodings."""

import pytest

from screamingface_engine.benchmarks.draco.validation import (
    has_text,
    optional_integer,
    require_positive_integer,
    require_text,
)


@pytest.mark.parametrize("value", [True, False, 1.5, None, [], {}])
def test_optional_integer_rejects_non_integer_json_shapes(value: object) -> None:
    assert optional_integer(value) is None


def test_integer_validation_accepts_integer_text_without_accepting_zero() -> None:
    assert optional_integer("12") == 12
    assert require_positive_integer(12, "case_id") == 12
    with pytest.raises(ValueError, match="case_id must be a positive integer"):
        require_positive_integer("0", "case_id")


def test_text_validation_preserves_content_but_rejects_blank_text() -> None:
    assert require_text("  answer  ", "answer") == "  answer  "
    assert has_text("answer") is True
    assert has_text("  ") is False
    with pytest.raises(ValueError, match="answer must be non-empty text"):
        require_text("  ", "answer")
