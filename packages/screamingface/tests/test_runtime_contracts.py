from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from dataclasses import replace

import httpx
import pytest

import screamingface as sf
import screamingface.engine as engine_module
import screamingface.evaluation as evaluation
import screamingface.results as results_module
import screamingface.session as session_module
from screamingface.data import load_mock_questions
from screamingface.engine import Url4EngineClient, parse_panel_result
from screamingface.model_inputs import normalize_model_inputs
from screamingface.results import ModelResult, Run, RunFailure


@pytest.fixture(autouse=True)
def _clean_runtime() -> Iterator[None]:
    sf.shutdown()
    yield
    sf.shutdown()


def _fusion() -> sf.Fusion:
    model_ids = tuple(sf.models.list()[:3])
    return sf.Fusion(
        "runtime-trio",
        model_ids,
        reducer=sf.MajorityVote(tie_breaker=model_ids[0]),
    )


def _panel_body(models: tuple[str, ...], answers: tuple[object, ...]) -> str:
    payload: dict[str, object] = {"schema": "screamingface.panel-result.v2"}
    for index, (model, answer) in enumerate(zip(models, answers, strict=True), 1):
        payload[f"panel_{index}_id"] = model
        payload[f"panel_{index}_model"] = model
        payload[f"panel_{index}_answer"] = answer
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_owned_engine_client_closes_after_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenClient:
        def __init__(self, **_kwargs) -> None:
            self.closed = False
            instances.append(self)

        async def get(self, _url: str, **_kwargs):
            raise httpx.ConnectError("connection refused")

        async def aclose(self) -> None:
            self.closed = True

    instances: list[BrokenClient] = []
    monkeypatch.setattr(engine_module.httpx, "AsyncClient", BrokenClient)

    with pytest.raises(sf.EngineUnavailable, match="unavailable"):
        await Url4EngineClient("http://engine.invalid").evaluate("('hello')")

    assert instances and instances[0].closed


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("not json", "non-JSON"),
        (json.dumps({"schema": "wrong"}), "must use schema"),
    ],
)
def test_panel_result_rejects_invalid_envelopes(body: str, message: str) -> None:
    with pytest.raises(sf.EngineError, match=message):
        parse_panel_result(
            body,
            normalize_model_inputs(("codex/gpt-5.5",)),
        )


def test_panel_result_requires_text_answers() -> None:
    with pytest.raises(sf.EngineError, match="must be text"):
        parse_panel_result(
            _panel_body(("codex/gpt-5.5",), (None,)),
            normalize_model_inputs(("codex/gpt-5.5",)),
        )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(500, text="plain failure"), ("engine_error", "HTTP 500")),
        (httpx.Response(502, json=["not", "an", "object"]), ("engine_error", "HTTP 502")),
        (
            httpx.Response(429, json={"error": {"code": 7, "message": False}}),
            ("engine_error", "HTTP 429"),
        ),
    ],
)
def test_engine_error_fallbacks(response: httpx.Response, expected: tuple[str, str]) -> None:
    code, message = engine_module._error_details(response)
    assert code == expected[0]
    assert expected[1] in message


class _StaticEngine:
    def __init__(self, body: str) -> None:
        self.body = body
        self.expressions: list[str] = []

    async def evaluate(self, expression: str) -> str:
        self.expressions.append(expression)
        return self.body


@pytest.mark.asyncio
async def test_evaluation_reports_progress_and_incomplete_answers() -> None:
    fusion = _fusion()
    question = load_mock_questions(1)[0]
    correct = chr(65 + question.answer)
    engine = _StaticEngine(_panel_body(fusion.model_ids, ("no answer", correct, correct)))
    updates: list[tuple[int, int, str]] = []
    session = sf.Session(engine=engine)

    run = await evaluation.evaluate(
        session=session,
        fusion=fusion,
        benchmark="gpqa",
        first=1,
        seed=0,
        progress=lambda *row: updates.append(row),
    )

    assert run.score == 100.0
    assert run.incomplete == 1
    assert run.failures == (
        RunFailure(
            question.id,
            fusion.model_ids[0],
            "invalid_answer",
            "Model did not return A-D",
            name=None,
        ),
    )
    assert run.model_results[0].failures == 1
    assert updates[0] == (0, 1, "Loading GPQA sample")
    assert updates[-1] == (1, 1, "Complete")
    assert len(engine.expressions) == 1


@pytest.mark.asyncio
async def test_evaluation_validates_benchmark_and_live_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    with pytest.raises(ValueError, match="only the 'gpqa'"):
        await evaluation.evaluate(
            session=sf.Session(),
            fusion=fusion,
            benchmark="other",
            first=1,
            seed=0,
        )

    expected = load_mock_questions(1)
    monkeypatch.setattr(evaluation, "load_live_questions", lambda first, seed: expected)
    assert evaluation._load_questions(sf.Session(mode="live"), 1, 4) == expected


@pytest.mark.asyncio
async def test_legacy_majority_processor_contract() -> None:
    process = evaluation._majority_processor(("one", "two", "three"), "two")
    assert await process("A\nB\nC", "majority_vote", None) == "B"
    with pytest.raises(ValueError, match="unsupported reducer"):
        await process("A\nB\nC", "merge", None)


def test_sync_evaluation_reports_terminal_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    updates: list[tuple[int, int, str]] = []

    def fail(_awaitable):
        _awaitable.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(
        evaluation,
        "_progress_reporter",
        lambda *_args: (
            lambda completed, total, message: updates.append((completed, total, message))
        ),
    )
    monkeypatch.setattr(session_module, "_run", fail)

    with pytest.raises(RuntimeError, match="boom"):
        evaluation.evaluate_sync(
            session=sf.Session(),
            fusion=_fusion(),
            benchmark="gpqa",
            first=2,
            seed=0,
        )

    assert updates[-1] == (0, 2, "Stopped with an error")


def test_progress_reporter_fallbacks(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(evaluation, "_in_notebook", lambda: False)
    assert evaluation._progress_reporter(None, 2, False) is None
    assert evaluation._progress_reporter(True, 2, True) is not None

    class MissingWidgets:
        def __init__(self, _total: int) -> None:
            raise ImportError

    monkeypatch.setattr(evaluation, "_NotebookProgress", MissingWidgets)
    reporter = evaluation._progress_reporter(True, 2, False)
    assert reporter is evaluation._text_progress
    assert reporter is not None
    reporter(2, 2, "Complete")
    assert "GPQA 2/2 · Complete" in capsys.readouterr().out


def test_session_replacement_lifecycle_and_sync_worker() -> None:
    first = sf.config()
    second = sf.config("http://engine.test", mode="live")

    assert first.closed
    assert second.dataset_source.startswith("gated:")
    assert "LIVE DATASET" in second._repr_html_()
    assert session_module._run(asyncio.sleep(0, result="done")) == "done"

    second.close()
    with pytest.raises(RuntimeError, match="closed"):
        session_module.require_session()

    sf.shutdown()
    assert sf.current_session() is None
    assert session_module._sync_executor is None
    assert session_module._worker_loop is None


def test_result_card_covers_mock_live_failure_and_name_variants() -> None:
    rows = (
        ModelResult("codex/gpt-5.5", 80.0, 0, 0, 0, 0.0, failures=1),
        ModelResult("custom_provider/my-api-2-0", 120.0, 0, 0, 0, 0.0),
    )
    mock = Run(
        benchmark="Fixture <unsafe>",
        dataset_source="fixture&source",
        mode="mock",
        models=tuple(row.model for row in rows),
        url="url4",
        sample_size=2,
        seed=0,
        score=100.0,
        baseline=80.0,
        gain=20.0,
        cost_usd=0.0,
        fusion_name="safe<script>",
        tie_breaker="codex/gpt-5.5",
        incomplete=1,
        pricing_as_of="n/a",
        model_results=rows,
        failures=(RunFailure("q1", rows[0].model, "invalid", "bad"),),
    )

    html = mock._repr_html_()
    assert "SIMULATED" not in html
    assert "safe&lt;script&gt;" in html
    assert "2 questions" in html
    assert "no provider-quality claim" in html
    assert "1 incomplete question rows" in html
    assert "OpenAI Codex" in html
    assert "Custom Provider" in html
    assert "width:100.0%" in html

    live = replace(
        mock,
        mode="live",
        gain=-2.0,
        cost_usd=1.23456,
        incomplete=0,
        failures=(),
        model_results=(),
        pricing_as_of="2026-07-16",
    )
    live_html = live._repr_html_()
    assert "$1.2346" in live_html
    assert "provider responses" in live_html
    assert "as of 2026-07-16" in live_html
    assert "#b3261e" in live_html

    assert "-5.0" in results_module._metric(-5.0, "negative")
