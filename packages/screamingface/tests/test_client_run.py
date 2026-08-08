"""Execution errors surfaced by the single Client.evaluate operation."""

from __future__ import annotations

import os
import signal
import threading
from datetime import UTC, datetime
from typing import NoReturn

import httpx
import pytest
from _model_parameter_fixtures import details as _model_details
from protocol_server import protocol_server
from url4 import RelExpr, expr, render, src, text

import screamingface as sf
from screamingface._core.ports import _RunOutcome
from screamingface._evaluation.model import Candidate

BENCHMARK_URL4 = render(
    expr(
        src(
            RelExpr(path="/candidate", context="question", intent=text("$candidate")),
            name="answer",
            weight=0.0,
        ),
        src(
            RelExpr(path="/provider/judge", context="$answer", intent=text("Grade.")),
            name="grade",
            weight=0.0,
        ),
        intent=text("$grade"),
    )
)

BENCHMARK = {
    "schema": "screamingface.benchmark.v1",
    "id": "draco",
    "variant": "canonical",
    "title": "DRACO",
    "description": "Fixture DRACO Benchmark.",
    "revision": "fixture-revision",
    "case_count": 1,
    "url4": BENCHMARK_URL4,
}


def _model_row(model: str) -> dict[str, object]:
    return {
        "id": model,
        "object": "model",
        "owned_by": model.split("/", 1)[0],
        "supported_parameters": [],
        "supported_tools": [],
        "unsupported_parameter_behavior": "reject",
        "parameter_contract_url": f"/v1/model-parameters?model={model}",
    }


def _engine(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        response = httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    _model_row("provider/opus"),
                    _model_row("provider/judge"),
                ],
            },
        )
    elif request.url.path == "/v1/benchmarks/draco":
        response = httpx.Response(200, json=BENCHMARK)
    elif request.url.path == "/v1/model-parameters":
        response = httpx.Response(200, json=_model_details(request.url.params["model"]))
    else:
        response = httpx.Response(404)
    return response


class _ForbiddenTransport:
    called = False

    def run(self, candidate: object, on_event: object) -> NoReturn:
        self.called = True
        raise AssertionError("unavailable Models must fail before execution")

    def cancel_active(self) -> None:
        pass

    def close(self) -> None:
        pass


class _InterruptibleTransport:
    """Two paid boundary calls that only cooperative cancellation can release promptly."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self.both_started = threading.Event()
        self.release = threading.Event()
        self.stopped_candidates: tuple[str, ...] = ()

    def run(self, candidate: Candidate, on_event: object) -> _RunOutcome:
        del on_event
        with self._lock:
            self._active.add(candidate.name)
            if len(self._active) == 2:
                self.both_started.set()
        try:
            self.release.wait(timeout=0.5)
            now = datetime.now(UTC)
            return _RunOutcome(
                run_id=candidate.name,
                started_at=now,
                completed_at=now,
                result_body="unused after interruption",
                media_type="text/plain",
                root_usage=None,
            )
        finally:
            with self._lock:
                self._active.remove(candidate.name)

    def cancel_active(self) -> None:
        with self._lock:
            self.stopped_candidates = tuple(sorted(self._active))
        self.release.set()

    def close(self) -> None:
        self.release.set()


def test_evaluate_rejects_an_unavailable_model_before_execution() -> None:
    def engine_without_candidate(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [_model_row("provider/judge")],
                },
            )
        return _engine(request)

    transport = _ForbiddenTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine_without_candidate),
        run_transport=transport,
    )

    with (
        client,
        pytest.raises(
            sf.PlanningError,
            match="Model 'missing/model' is not available on this Engine",
        ) as caught,
    ):
        client.evaluate(sf.Model("missing/model"), benchmark="draco")

    assert caught.value.code == "model_unavailable"
    assert caught.value.permanent is True
    assert caught.value.details == {"models": ["missing/model"]}
    assert transport.called is False


def test_evaluate_rejects_an_unavailable_fusion_model_before_execution() -> None:
    def engine_without_synthesis(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        _model_row(model)
                        for model in ("provider/opus", "provider/gpt", "provider/judge")
                    ],
                },
            )
        return _engine(request)

    fusion = sf.Fusion(
        [sf.Model("provider/opus"), sf.Model("provider/gpt")],
        name="panel",
        synthesizer="provider/synthesis",
    )
    transport = _ForbiddenTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine_without_synthesis),
        run_transport=transport,
    )

    with (
        client,
        pytest.raises(
            sf.PlanningError,
            match="Model 'provider/synthesis' is not available on this Engine",
        ),
    ):
        client.evaluate(fusion, benchmark="draco")

    assert transport.called is False


def test_evaluate_reports_an_unreachable_execution_transport() -> None:
    with sf.Client(
        engine_url="http://127.0.0.1:1",
        http_transport=httpx.MockTransport(_engine),
    ) as client:
        with pytest.raises(sf.EngineUnavailableError) as caught:
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark="draco",
                progress=False,
            )

    assert caught.value.code == "engine_unreachable"
    assert caught.value.permanent is False
    assert caught.value.engine_url == "http://127.0.0.1:1"


def test_interrupting_concurrent_candidates_stops_every_active_engine_run() -> None:
    transport = _InterruptibleTransport()

    def interrupt_after_both_runs_start() -> None:
        if transport.both_started.wait(timeout=1):
            os.kill(os.getpid(), signal.SIGINT)

    interrupter = threading.Thread(target=interrupt_after_both_runs_start, daemon=True)
    interrupter.start()
    with (
        sf.Client(
            engine_url="https://engine.example",
            http_transport=httpx.MockTransport(_engine),
            run_transport=transport,
        ) as client,
        pytest.raises(KeyboardInterrupt),
    ):
        client.evaluate(
            [
                sf.Model("provider/opus", name="left"),
                sf.Model("provider/opus", name="right"),
            ],
            benchmark="draco",
            progress=False,
        )
    interrupter.join(timeout=1)

    assert interrupter.is_alive() is False
    assert transport.stopped_candidates == ("left", "right")


def test_concurrent_interrupt_deletes_every_active_engine_capability() -> None:
    with protocol_server(mode="http_stop") as engine:

        def interrupt_after_both_runs_start() -> None:
            if engine.state.two_started.wait(timeout=1):
                os.kill(os.getpid(), signal.SIGINT)

        interrupter = threading.Thread(target=interrupt_after_both_runs_start, daemon=True)
        interrupter.start()
        with (
            sf.Client(
                engine_url=engine.url,
                http_transport=httpx.MockTransport(_engine),
            ) as client,
            pytest.raises(KeyboardInterrupt),
        ):
            client.evaluate(
                [
                    sf.Model("provider/opus", name="left"),
                    sf.Model("provider/opus", name="right"),
                ],
                benchmark="draco",
                progress=False,
            )
        interrupter.join(timeout=1)

    assert interrupter.is_alive() is False
    assert len(engine.state.minted_tokens) == 2
    assert sorted(engine.state.deleted_tokens) == sorted(engine.state.minted_tokens)


@pytest.mark.asyncio
async def test_async_evaluate_reports_the_same_unreachable_execution_transport() -> None:
    client = sf.AsyncClient(
        engine_url="http://127.0.0.1:1",
        http_transport=httpx.MockTransport(_engine),
    )

    with pytest.raises(sf.EngineUnavailableError) as caught:
        await client.evaluate(
            sf.Model("provider/opus"),
            benchmark="draco",
            progress=False,
        )
    await client.aclose()

    assert caught.value.retryable is True
    assert caught.value.engine_url == "http://127.0.0.1:1"
