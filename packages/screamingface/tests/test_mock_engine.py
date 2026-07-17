from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

import screamingface as sf
from screamingface._mock_engine import MockUrl4Engine, mock_model_answer


@pytest.fixture(autouse=True)
def _clean_runtime() -> Iterator[None]:
    sf.shutdown()
    yield
    sf.shutdown()


def _panel_models() -> list[str]:
    return [
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    ]


def test_zero_setup_gpqa_executes_complete_expressions_in_process() -> None:
    fusion = sf.Fusion(
        "zero-setup",
        _panel_models(),
        reducer=sf.MajorityVote(tie_breaker="codex/gpt-5.5"),
    )

    run = fusion.evaluate("gpqa", first=20, seed=0)
    session = sf.current_session()

    assert run.score == 100.0
    assert run.baseline == 80.0
    assert run.gain == 20.0
    assert run.engine == "mock"
    assert session is not None
    assert isinstance(session.engine, MockUrl4Engine)
    assert len(session.engine.expressions) == 20
    assert all("screamingface.panel-result.v2" in value for value in session.engine.expressions)


def test_zero_setup_model_reducer_uses_the_same_url4_node() -> None:
    fusion = sf.Fusion(
        "model-reduced",
        _panel_models()[:2],
        reducer=sf.ModelReducer(
            model="codex/gpt-5.5",
            prompt="Choose one answer for $question from $panel_answers",
            params={"temperature": 0.0},
        ),
    )

    run = fusion.evaluate("gpqa", first=1, seed=0)
    session = sf.current_session()

    assert run.sample_size == 1
    assert session is not None
    assert isinstance(session.engine, MockUrl4Engine)
    assert len(session.engine.expressions) == 1
    assert "screamingface.fusion-result.v2" in session.engine.expressions[0]


def test_zero_setup_draco_executes_panel_reducer_and_judges() -> None:
    fusion = sf.Fusion(
        "draco-zero-setup",
        _panel_models(),
        prompt="Research and answer: $question",
        tools=["web_search"],
        reducer=sf.ModelReducer(
            model="codex/gpt-5.5",
            prompt="Write a unified panel answer for $question from $panel_answers",
        ),
    )

    run = fusion.evaluate("draco", first=1, seed=0)
    session = sf.current_session()

    assert run.primary_metric == "normalized_score"
    assert dict(run.metrics)["verdict_coverage"] == 100.0
    assert session is not None
    assert isinstance(session.engine, MockUrl4Engine)
    assert len(session.engine.expressions) > 1
    assert any("reasoning=low" in value for value in session.engine.expressions)


def test_leaf_mock_has_stable_generic_and_multiple_choice_fallbacks() -> None:
    generic = mock_model_answer("codex/gpt-5.5", "Explain an unfamiliar topic")
    assert generic == mock_model_answer("codex/gpt-5.5", "Explain an unfamiliar topic")
    assert "Deterministic mock response" in generic

    choice = mock_model_answer(
        "gemini-cli/gemini-2.5-pro",
        "A. one\nB. two\nC. three\nD. four\nReply with only A, B, C, or D.",
    )
    assert choice in {"A", "B", "C", "D"}


def test_leaf_mock_handles_generic_synthesis_and_rubric_verdicts() -> None:
    synthesis = mock_model_answer(
        "codex/gpt-5.5",
        "Produce a unified response from the panel: alpha and beta.",
    )
    assert synthesis == "Unified research response: alpha, beta"

    context = (
        "<criterion_type>positive</criterion_type>\n"
        "<criterion>Give a clear answer</criterion>\n"
        "<response>A clear answer</response>"
    )
    verdict = json.loads(mock_model_answer("google/gemini-3.1-pro-preview", "Judge", context))
    assert verdict["criterion_status"] in {"MET", "UNMET"}
    assert verdict["explanation"] == "deterministic mock rubric verdict"


def test_leaf_mock_rejects_unknown_models_and_malformed_judge_context() -> None:
    with pytest.raises(ValueError, match="unknown mock model"):
        mock_model_answer("provider/missing", "prompt")
    with pytest.raises(ValueError, match="invalid deterministic DRACO judge prompt"):
        mock_model_answer(
            "google/gemini-3.1-pro-preview",
            "Judge",
            "<criterion_type>positive</criterion_type><response>answer</response>",
        )
