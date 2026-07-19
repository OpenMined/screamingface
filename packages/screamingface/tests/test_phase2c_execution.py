from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import httpx
import pytest

import screamingface as sf
from screamingface import _execution
from screamingface._compiler import compile_fusion
from screamingface._profile import ModelRecord, ReducerRecord, Registry


def _registry(
    *,
    models: tuple[ModelRecord, ...] | None = None,
    reducers: tuple[ReducerRecord, ...] | None = None,
) -> Registry:
    return Registry(
        models=models
        or (
            ModelRecord("codex/gpt-5.5", ()),
            ModelRecord("gemini/2.5", ()),
            ModelRecord("judge/model", ()),
        ),
        reducers=reducers
        if reducers is not None
        else (ReducerRecord("majority_vote", "/reducers/majority-vote"),),
        benchmarks=(),
        response_schemas=("screamingface.fusion-result.v1",),
    )


def _fusion(reducer=None) -> sf.Fusion:
    return sf.Fusion(
        "frontier",
        ["codex/gpt-5.5", "gemini/2.5"],
        reducer=reducer or sf.reducers.MajorityVote(),
    )


def _benchmark(count: int = 1, *, tools: tuple[str, ...] = ()) -> sf.Benchmark:
    return sf.Benchmark(
        "tiny@1",
        cases=[sf.Case(f"q{index}", f"Question {index}", reference="A") for index in range(count)],
        grader=sf.graders.ExactChoice(),
        tools=tools,
    )


def _success(fusion: sf.Fusion, case_id: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=json.dumps(
            {
                "answer": f"answer-{case_id}",
                "members": {
                    "panel_2": {"answer": "B", "model": "gemini/2.5"},
                    "panel_1": {"model": "codex/gpt-5.5", "answer": "A"},
                },
                "schema": "screamingface.fusion-result.v1",
            }
        ),
        headers={"content-type": "text/plain; charset=utf-8"},
        request=httpx.Request("GET", "http://engine.test/v1"),
    )


class FakeClient:
    def __init__(
        self,
        responses: dict[str, Callable[[], httpx.Response]],
        *,
        delay: float = 0,
    ) -> None:
        self.responses = responses
        self.delay = delay
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        assert path == "/v1"
        expression = params["q"]
        with self._lock:
            self.calls.append(expression)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.responses[expression]()
        finally:
            with self._lock:
                self.active -= 1


def _install(
    monkeypatch: pytest.MonkeyPatch,
    fusion: sf.Fusion,
    benchmark: sf.Benchmark,
    response: Callable[[str], httpx.Response] | None = None,
    *,
    delay: float = 0,
) -> FakeClient:
    monkeypatch.setattr(_execution, "load_registry", _registry)
    responses = {
        compile_fusion(fusion, question=case.input): (
            lambda case_id=case.id: response(case_id) if response else _success(fusion, case_id)
        )
        for case in benchmark._materialize_cases()
    }
    client = FakeClient(responses, delay=delay)
    monkeypatch.setattr(_execution.httpx, "Client", lambda **_kwargs: client)
    return client


def test_run_executes_one_request_per_case_with_bounded_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark(6)
    client = _install(monkeypatch, fusion, benchmark, delay=0.02)

    run = fusion.run(benchmark, first=5)

    assert run.case_ids == ("q0", "q1", "q2", "q3", "q4")
    assert tuple(result.answer for result in run.results) == tuple(
        f"answer-q{index}" for index in range(5)
    )
    assert tuple(run.results[0].members) == ("panel_1", "panel_2")
    assert len(client.calls) == 5
    assert 2 <= client.max_active <= 4
    assert run.fusion_url4 == fusion.url4
    assert run.complete is True


def test_structured_failures_are_not_retried_or_made_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark(3)

    def overloaded(_case_id: str) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "overloaded", "message": "try later"}},
            request=httpx.Request("GET", "http://engine.test/v1"),
        )

    client = _install(monkeypatch, fusion, benchmark, overloaded)

    run = fusion.run(benchmark)

    assert len(client.calls) == 3
    assert [failure.kind for failure in run.failures] == ["url4"] * 3
    assert [failure.code for failure in run.failures] == ["overloaded"] * 3
    assert all(result.members == {} and result.answer is None for result in run.results)


def test_named_benchmark_uses_the_preflight_registry_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark()
    registry = _registry()
    calls: list[tuple[str, Registry]] = []
    monkeypatch.setattr(_execution, "load_registry", lambda: registry)
    monkeypatch.setattr(
        _execution,
        "load_benchmark_from_registry",
        lambda benchmark_id, snapshot: calls.append((benchmark_id, snapshot)) or benchmark,
    )
    _install(monkeypatch, fusion, benchmark)
    monkeypatch.setattr(_execution, "load_registry", lambda: registry)

    run = fusion.run("tiny@1")

    assert run.benchmark_id == "tiny@1"
    assert calls == [("tiny@1", registry)]


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (httpx.ConnectError("offline"), "connection"),
        (httpx.ReadTimeout("late"), "timeout"),
    ],
)
def test_transport_failures_are_safe_case_results(error: Exception, kind: str) -> None:
    class BrokenClient:
        def get(self, _path: str, *, params: dict[str, str]) -> httpx.Response:
            assert params["q"]
            raise error

    case = sf.Case("q", "Question", reference="A")
    result = _execution._execute_case(
        BrokenClient(),  # type: ignore[arg-type]
        _fusion(),
        case,
        compile_fusion(_fusion(), question=case.input),
    )

    assert result.failure is not None
    assert result.failure.kind == kind
    assert "offline" not in result.failure.message


@pytest.mark.parametrize(
    ("response", "kind", "code"),
    [
        (
            httpx.Response(
                504,
                json={"error": {"code": "timeout", "message": "late"}},
                request=httpx.Request("GET", "http://engine.test/v1"),
            ),
            "timeout",
            "timeout",
        ),
        (
            httpx.Response(
                418,
                text="provider body must not leak",
                request=httpx.Request("GET", "http://engine.test/v1"),
            ),
            "http",
            None,
        ),
        (
            httpx.Response(
                200,
                text="not json",
                headers={"content-type": "text/plain"},
                request=httpx.Request("GET", "http://engine.test/v1"),
            ),
            "protocol",
            None,
        ),
        (
            httpx.Response(
                200,
                text="{}",
                headers={"content-type": "application/json"},
                request=httpx.Request("GET", "http://engine.test/v1"),
            ),
            "protocol",
            None,
        ),
    ],
)
def test_response_failure_categories(response: httpx.Response, kind: str, code: str | None) -> None:
    result = _execution._response_result("q", _fusion(), response)

    assert result.failure is not None
    assert result.failure.kind == kind
    assert result.failure.code == code
    assert "provider body" not in result.failure.message


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema="wrong"),
        lambda value: value.update(extra=True),
        lambda value: value["members"].pop("panel_2"),
        lambda value: value["members"]["panel_1"].update(model="wrong"),
        lambda value: value["members"]["panel_1"].update(answer=" "),
        lambda value: value.update(answer=""),
    ],
)
def test_success_contract_is_strict(mutate) -> None:
    response = _success(_fusion(), "q")
    payload = response.json()
    mutate(payload)
    invalid = httpx.Response(
        200,
        json=payload,
        headers={"content-type": "text/plain"},
        request=response.request,
    )

    result = _execution._response_result("q", _fusion(), invalid)

    assert result.failure is not None
    assert result.failure.kind == "protocol"


def test_preflight_rejects_unknown_models_tools_reducers_and_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark(tools=("web_search",))
    monkeypatch.setattr(_execution, "load_registry", _registry)

    with pytest.raises(sf.UnsupportedToolError, match="web_search"):
        fusion.run(benchmark)

    monkeypatch.setattr(
        _execution,
        "load_registry",
        lambda: _registry(models=(ModelRecord("codex/gpt-5.5", ()),)),
    )
    with pytest.raises(sf.UnknownModelError, match="gemini"):
        fusion.run(_benchmark())

    monkeypatch.setattr(
        _execution,
        "load_registry",
        lambda: _registry(reducers=()),
    )
    with pytest.raises(sf.UnsupportedReducerError, match="majority-vote"):
        fusion.run(_benchmark())

    monkeypatch.setattr(_execution, "load_registry", _registry)
    missing_reference = sf.Benchmark(
        "bad",
        cases=[sf.Case("q", "Question")],
        grader=sf.graders.ExactChoice(),
    )
    with pytest.raises(sf.InvalidBenchmarkError, match="reference"):
        fusion.run(missing_reference)


@pytest.mark.parametrize("first", [0, -1, True, 1.5])
def test_first_is_validated_before_network(first: object) -> None:
    with pytest.raises(ValueError, match="first"):
        _fusion().run(_benchmark(), first=first)  # type: ignore[arg-type]
