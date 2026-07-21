from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import httpx
import pytest

import screamingface as sf
from screamingface import _execution, connections
from screamingface._compiler import compile_recipe
from screamingface._profile import ModelRecord, ProviderRecord, ReducerRecord, Registry


def _registry(
    *,
    models: tuple[ModelRecord, ...] | None = None,
    reducers: tuple[ReducerRecord, ...] | None = None,
) -> Registry:
    return Registry(
        models=models
        or (
            ModelRecord("codex/gpt-5.5", (), "codex"),
            ModelRecord("gemini/2.5-flash", (), "gemini"),
            ModelRecord("judge/model", (), "judge"),
        ),
        reducers=reducers
        if reducers is not None
        else (ReducerRecord("majority_vote", "/reducers/majority-vote"),),
        response_schemas=("screamingface.recipe-result.v1",),
        max_request_target_bytes=61440,
        providers=(
            ProviderRecord("codex", "OpenAI Codex", ("oauth",)),
            ProviderRecord("gemini", "Google Gemini", ("oauth", "api_key")),
            ProviderRecord("judge", "Judge", ("api_key",)),
            ProviderRecord("tavily", "Tavily", ("api_key",)),
        ),
    )


@pytest.fixture(autouse=True)
def _connected_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    sf.config(engine="http://127.0.0.1:4404")

    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/connections"
        return httpx.Response(
            200,
            json={
                "schema": "screamingface.connections.v1",
                "connections": [
                    {
                        "provider": provider.id,
                        "status": "connected",
                        "auth_method": provider.auth_methods[0],
                        "account_label": None,
                    }
                    for provider in _registry().providers
                ],
            },
        )

    monkeypatch.setattr(connections, "_transport", httpx.MockTransport(response))


def _fusion(reducer=None) -> sf.Fusion:
    return sf.Fusion(
        "frontier",
        members=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=reducer or sf.reducers.MajorityVote(),
    )


def _benchmark(
    count: int = 1,
    *,
    tools: tuple[sf.tools.Tool, ...] = (),
) -> sf.Benchmark:
    return sf.Benchmark(
        "tiny@1",
        cases=[sf.Case(f"q{index}", f"Question {index}", reference="A") for index in range(count)],
        grader=sf.graders.ExactChoice(),
        tools=tools,
        max_tool_rounds=8 if tools else None,
    )


def _success(fusion: sf.Fusion, case_id: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=json.dumps(
            {
                "answer": f"answer-{case_id}",
                "members": {
                    "member_2": {"answer": "B", "model": "gemini/2.5-flash"},
                    "member_1": {"model": "codex/gpt-5.5", "answer": "A"},
                },
                "schema": "screamingface.recipe-result.v1",
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
        compile_recipe(
            fusion,
            question=case.input,
            tools=benchmark.tools,
            max_tool_rounds=benchmark.max_tool_rounds,
        ): (lambda case_id=case.id: response(case_id) if response else _success(fusion, case_id))
        for case in benchmark._materialize_cases()
    }
    client = FakeClient(responses, delay=delay)
    monkeypatch.setattr(_execution.httpx, "Client", lambda **_kwargs: client)
    return client


def test_supported_benchmark_tools_are_sent_only_in_concrete_member_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark(tools=(sf.tools.TavilySearch(),))
    supported = (
        ModelRecord("codex/gpt-5.5", ("web_search",), "codex"),
        ModelRecord("gemini/2.5-flash", ("web_search",), "gemini"),
        ModelRecord("judge/model", (), "judge"),
    )
    monkeypatch.setattr(_execution, "load_registry", lambda: _registry(models=supported))
    client = _install(monkeypatch, fusion, benchmark)
    monkeypatch.setattr(_execution, "load_registry", lambda: _registry(models=supported))

    run = fusion.run(benchmark)

    assert len(client.calls) == 1
    expression = client.calls[0]
    assert expression.count("tools=web_search") == 2
    assert expression.count("max_tool_rounds=8") == 2
    assert "recipe_answer=/reducers/majority-vote($member_answers)" in expression
    assert run.recipe_url4 == fusion.url4
    assert "tools=" not in run.recipe_url4


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
    assert tuple(run.results[0].members) == ("member_1", "member_2")
    assert len(client.calls) == 5
    assert 2 <= client.max_active <= 4
    assert run.recipe_url4 == fusion.url4
    assert run.complete is True


def test_structured_transient_canary_is_retried_once_without_partial_results(
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

    assert len(client.calls) == 2
    assert [failure.kind for failure in run.failures] == ["url4", "skipped", "skipped"]
    assert [failure.code for failure in run.failures] == [
        "overloaded",
        "not_scheduled",
        "not_scheduled",
    ]
    assert all(result.members == {} and result.answer is None for result in run.results)


def test_named_benchmark_loads_locally_before_engine_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = _fusion()
    benchmark = _benchmark()
    registry = _registry()
    calls: list[str] = []
    monkeypatch.setattr(_execution, "load_registry", lambda: registry)
    monkeypatch.setattr(
        _execution,
        "load_benchmark",
        lambda benchmark_id: calls.append(benchmark_id) or benchmark,
    )
    _install(monkeypatch, fusion, benchmark)
    monkeypatch.setattr(_execution, "load_registry", lambda: registry)

    run = fusion.run("tiny@1")

    assert run.benchmark_id == "tiny@1"
    assert calls == ["tiny@1"]


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
        compile_recipe(_fusion(), question=case.input),
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
        lambda value: value["members"].pop("member_2"),
        lambda value: value["members"]["member_1"].update(model="wrong"),
        lambda value: value["members"]["member_1"].update(answer=" "),
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
    benchmark = _benchmark(tools=(sf.tools.TavilySearch(),))
    monkeypatch.setattr(_execution, "load_registry", _registry)

    with pytest.raises(sf.UnsupportedToolError, match="web_search"):
        fusion.run(benchmark)

    monkeypatch.setattr(
        _execution,
        "load_registry",
        lambda: _registry(models=(ModelRecord("codex/gpt-5.5", (), "codex"),)),
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
