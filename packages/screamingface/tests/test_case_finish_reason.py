"""The public Case Result preserves how its selected Candidate output ended."""

from __future__ import annotations

import pytest

import screamingface as sf


def _case(finish_reason: str | None) -> sf.CaseResult:
    return sf.CaseResult(
        case_id=1,
        input="Explain the result.",
        output="The result follows because",
        finish_reason=finish_reason,
        grade=sf.CaseGrade(method="fixture", score=0.0, metrics={}, checks=()),
        failures=(),
        metadata={},
    )


def test_finish_reason_is_directly_visible_and_always_serialized() -> None:
    case = _case("length")

    assert case.finish_reason == "length"
    assert case.to_dict()["finish_reason"] == "length"


def test_an_omitted_provider_reason_remains_explicit_null() -> None:
    case = _case(None)

    assert case.finish_reason is None
    assert "finish_reason" in case.to_dict()
    assert case.to_dict()["finish_reason"] is None


@pytest.mark.parametrize("finish_reason", ["", "   "])
def test_finish_reason_rejects_blank_text(finish_reason: str) -> None:
    with pytest.raises(ValueError, match="finish_reason"):
        _case(finish_reason)
