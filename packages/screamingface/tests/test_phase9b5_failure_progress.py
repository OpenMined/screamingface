from __future__ import annotations

from types import SimpleNamespace

import pytest

import screamingface as sf
from screamingface import _execution, _progress
from screamingface.run import CaseResult, Run, RunFailure


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def stage(self, stage: str, label: str, *, total: int | None = None) -> None:
        self.events.append(("stage", stage, label, total))

    def advance(self, count: int = 1) -> None:
        self.events.append(("advance", count))

    def finish(self, label: str = "Complete") -> None:
        self.events.append(("finish", label))

    def stop(self, label: str, *, completed: int, total: int) -> None:
        self.events.append(("stop", label, completed, total))

    def fail(self, message: str) -> None:
        self.events.append(("fail", message))


def _benchmark() -> sf.Benchmark:
    return sf.Benchmark(
        "tiny@1",
        cases=[sf.Case("q1", "Question", reference="A")],
        grader=sf.graders.ExactChoice(),
    )


def _fusion() -> sf.Fusion:
    return sf.Fusion(
        "research-duo",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )


def _failed_run(fusion: sf.Fusion, benchmark: sf.Benchmark) -> Run:
    failure = RunFailure(
        "q1",
        "url4",
        "tool budget exhausted",
        status=422,
        code="tool_budget_exhausted",
    )
    return Run(
        benchmark=benchmark,
        recipe_name=fusion.name,
        recipe_url4=fusion.url4,
        members=(("member_1", fusion.model_ids[0]), ("member_2", fusion.model_ids[1])),
        cases=benchmark._materialize_cases(),
        results=(CaseResult("q1", members=(), answer=None, failure=failure),),
    )


def test_incomplete_evaluate_skips_empty_grading_progress_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark()
    tracker = _Recorder()
    monkeypatch.setattr(_execution, "Progress", lambda *_args, **_kwargs: tracker)
    monkeypatch.setattr(_execution, "load_registry", lambda: SimpleNamespace())
    monkeypatch.setattr(_execution, "_preflight", lambda *_args: None)
    monkeypatch.setattr(_execution, "evaluate_requirements", lambda *_args: ())
    monkeypatch.setattr(_execution, "require_connections", lambda *_args: None)
    monkeypatch.setattr(
        _execution,
        "run_recipe",
        lambda *_args, **_kwargs: _failed_run(fusion, benchmark),
    )

    report = fusion.evaluate(benchmark, progress=True)

    assert report.complete is False
    assert not any(event[:2] == ("stage", "grading") for event in tracker.events)
    assert tracker.events[-1] == (
        "stop",
        "0/1 cases scored · 1 attempted",
        0,
        1,
    )
    assert not any(event[0] == "finish" for event in tracker.events)


def test_stopped_progress_is_a_terminal_accessible_receipt() -> None:
    state = _progress._State(
        "research-duo",
        "draco-preview@1",
        "stopped",
        "0/1 cases scored · 1 attempted",
        completed=0,
        total=1,
    )

    html = _progress.progress_html(state)

    assert "class='sf-progress__status stopped'" in html
    assert "0/1 cases scored · 1 attempted" in html
    assert "aria-valuenow='0'" in html
