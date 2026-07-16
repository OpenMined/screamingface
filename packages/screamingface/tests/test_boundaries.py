from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

import screamingface as sf
import screamingface.data as data
import screamingface.evaluation as evaluation
import screamingface.session as session_module
from screamingface.errors import DatasetUnavailable


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def test_question_loading_boundaries_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    question = data.load_mock_questions(1)[0]
    assert "A." in question.prompt()
    assert "Reply with only A, B, C, or D." in question.prompt()
    with pytest.raises(ValueError, match="positive"):
        data.load_mock_questions(0)
    with pytest.raises(ValueError, match="contains 20"):
        data.load_mock_questions(21)

    monkeypatch.setattr(data, "import_module", lambda _name: (_ for _ in ()).throw(ImportError()))
    with pytest.raises(DatasetUnavailable, match="datasets"):
        data.load_live_questions(1, 0)


def test_live_question_loading_is_seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "Question": "Which option is correct?",
            "Correct Answer": "right",
            "Incorrect Answer 1": "wrong 1",
            "Incorrect Answer 2": "wrong 2",
            "Incorrect Answer 3": "wrong 3",
        }
    ]
    loader = SimpleNamespace(load_dataset=lambda *args, **kwargs: rows)
    monkeypatch.setattr(data, "import_module", lambda _name: loader)

    first = data.load_live_questions(1, 7)[0]
    second = data.load_live_questions(1, 7)[0]
    assert first == second
    assert first.options[first.answer] == "right"


def test_setup_is_optional_and_only_configures_url4_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCREAMINGFACE_ENGINE_URL", "http://engine.test:4404")

    assert sf.models.list()
    assert sf.current_session() is None
    session = session_module.require_session()
    assert session.engine_url == "http://engine.test:4404"
    assert session.mode == "mock"
    assert "URL4 engine" in session._repr_html_()


def test_explicit_setup_overrides_engine_and_validates_mode() -> None:
    session = sf.config("http://other.test:9000")

    assert session.engine_url == "http://other.test:9000"
    assert sf.current_session() is session
    with pytest.raises(ValueError, match="mode"):
        sf.config(mode=cast(session_module.Mode, "invalid"))


def test_fusion_and_reducer_validation() -> None:
    ids = sf.models.list()
    with pytest.raises(ValueError, match="empty"):
        sf.Fusion(" ", ids[:2])
    with pytest.raises(ValueError, match="at least two"):
        sf.Fusion("one", ids[:1])
    with pytest.raises(ValueError, match="unknown"):
        sf.Fusion("unknown", [ids[0], "vendor/missing"])
    with pytest.raises(ValueError, match="tie_breaker"):
        sf.Fusion("bad", ids[:2], reducer=sf.MajorityVote(tie_breaker=ids[2]))


def test_answer_normalization_and_vote_boundaries() -> None:
    models = ("one", "two", "three")

    assert evaluation.normalize_answer("Answer: b") == "B"
    assert evaluation.normalize_answer("no selection") == ""
    assert evaluation.majority_vote(("A", "B", "C"), models, "three") == "C"
    assert evaluation.majority_vote(("A", "B", "B"), models, "one") == "B"
    assert evaluation.majority_vote(("", "", ""), models, None) == ""


def test_notebook_progress_describes_engine_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    displayed: list[object] = []
    monkeypatch.setattr("IPython.display.display", displayed.append)

    progress = evaluation._NotebookProgress(2)
    progress.update(1, 2, "Question 1/2")

    assert displayed
    assert progress._bar.description == "Questions"
    assert progress._bar.value == 1
    assert "one URL4 engine request" in progress._status.value
