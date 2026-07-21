from __future__ import annotations

import json
from collections.abc import Mapping

import httpx
import pytest

import screamingface as sf
from screamingface import _execution, _grading, connections
from screamingface._profile import ModelRecord, ProviderRecord, ReducerRecord, Registry


def _registry() -> Registry:
    return Registry(
        models=(
            ModelRecord("codex/gpt-5.5", (), "codex"),
            ModelRecord("gemini/2.5-flash", (), "gemini"),
            ModelRecord("judge/model", (), "judge"),
        ),
        reducers=(ReducerRecord("majority_vote", "/reducers/majority-vote"),),
        response_schemas=("screamingface.fusion-result.v1",),
        max_request_target_bytes=61440,
        providers=(
            ProviderRecord("codex", "OpenAI Codex", ("oauth",)),
            ProviderRecord("gemini", "Google Gemini", ("oauth", "api_key")),
            ProviderRecord("judge", "Judge Provider", ("api_key",)),
        ),
    )


def _fusion() -> sf.Fusion:
    return sf.Fusion(
        "panel",
        inputs=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )


def _reference() -> dict[str, object]:
    return {
        "sections": [
            {
                "id": "quality",
                "criteria": [
                    {"id": "correct", "requirement": "The answer is correct.", "weight": 1}
                ],
            }
        ]
    }


def _benchmark(*, rubric: bool = False, count: int = 1) -> sf.Benchmark:
    reference: object = _reference() if rubric else "A"
    grader: sf.Grader = (
        sf.graders.Rubric(model="judge/model", prompt="Judge $answer", passes=1)
        if rubric
        else sf.graders.ExactChoice()
    )
    return sf.Benchmark(
        "tiny@1",
        cases=[
            sf.Case(f"q{index}", f"Question {index}", reference=reference) for index in range(count)
        ],
        grader=grader,
    )


class EngineClient:
    def __init__(self, statuses: Mapping[str, str]) -> None:
        self.statuses = dict(statuses)
        self.status_reads = 0
        self.eval_calls: list[str] = []
        self.fail_fusion_auth = False
        self.fail_judge_auth = False

    def __enter__(self) -> EngineClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def connection_response(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/connections"
        self.status_reads += 1
        return httpx.Response(
            200,
            json={
                "schema": "screamingface.connections.v1",
                "connections": [
                    {
                        "provider": provider.id,
                        "status": self.statuses[provider.id],
                        "auth_method": (
                            provider.auth_methods[0]
                            if self.statuses[provider.id] == "connected"
                            else None
                        ),
                        "account_label": None,
                    }
                    for provider in _registry().providers
                ],
            },
            request=request,
        )

    def get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        assert path == "/v1"
        expression = params["q"]
        self.eval_calls.append(expression)
        if ("member_1=" in expression and self.fail_fusion_auth) or (
            "member_1=" not in expression and self.fail_judge_auth
        ):
            return httpx.Response(
                401,
                json={
                    "error": {
                        "code": "connection_needs_reauth",
                        "message": "Reconnect the provider.",
                    }
                },
                request=httpx.Request("GET", "http://engine.test/v1"),
            )
        if "member_1=" in expression:
            body = {
                "schema": "screamingface.fusion-result.v1",
                "members": {
                    "member_1": {"model": "codex/gpt-5.5", "answer": "A"},
                    "member_2": {"model": "gemini/2.5-flash", "answer": "A"},
                },
                "answer": "A",
            }
            return httpx.Response(
                200,
                text=json.dumps(body),
                headers={"content-type": "text/plain"},
                request=httpx.Request("GET", "http://engine.test/v1"),
            )
        return httpx.Response(
            200,
            text='{"explanation":"Correct.","criterion_status":"MET"}',
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "http://engine.test/v1"),
        )


def _install(monkeypatch: pytest.MonkeyPatch, statuses: Mapping[str, str]) -> EngineClient:
    client = EngineClient(statuses)
    monkeypatch.setattr(_execution, "load_registry", _registry)
    monkeypatch.setattr(_grading, "load_registry", _registry)
    monkeypatch.setattr(_execution.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(
        connections,
        "_transport",
        httpx.MockTransport(client.connection_response),
    )
    sf.config(engine="http://127.0.0.1:4404")
    return client


def test_run_requires_only_member_and_reducer_connections_before_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "not_connected", "judge": "not_connected"},
    )

    with pytest.raises(sf.ConnectionRequiredError) as captured:
        _fusion().run(_benchmark(rubric=True))

    error = captured.value
    assert error.providers == ("gemini",)
    assert error.models == ("gemini/2.5-flash",)
    assert error.roles == ("member",)
    assert "sf.connect('gemini'" in str(error)
    assert client.status_reads == 1
    assert client.eval_calls == []


def test_run_ignores_disconnected_judge_but_grade_checks_it_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "not_connected"},
    )
    run = _fusion().run(_benchmark(rubric=True))

    assert len(client.eval_calls) == 1
    with pytest.raises(sf.ConnectionRequiredError) as captured:
        run.grade()

    assert captured.value.providers == ("judge",)
    assert captured.value.models == ("judge/model",)
    assert captured.value.roles == ("grader",)
    assert client.status_reads == 2
    assert len(client.eval_calls) == 1


def test_evaluate_checks_the_union_once_before_any_model_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "not_connected"},
    )

    with pytest.raises(sf.ConnectionRequiredError) as captured:
        _fusion().evaluate(_benchmark(rubric=True))

    assert captured.value.providers == ("judge",)
    assert client.status_reads == 1
    assert client.eval_calls == []


def test_connected_evaluate_does_not_repeat_nested_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "connected"},
    )

    report = _fusion().evaluate(_benchmark(rubric=True))

    assert report.n_scored == 1
    assert client.status_reads == 1
    assert len(client.eval_calls) == 4


def test_evaluate_emits_one_coherent_run_grade_aggregate_progress_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "connected"},
    )
    events: list[tuple[object, ...]] = []

    class Recorder:
        stage_name = ""

        def stage(self, stage: str, label: str, *, total: int | None = None) -> None:
            self.stage_name = stage
            events.append(("stage", stage, label, total))

        def advance(self, count: int = 1) -> None:
            events.append(("advance", self.stage_name, count))

        def finish(self, label: str = "Complete") -> None:
            events.append(("finish", label))

        def fail(self, message: str) -> None:
            events.append(("fail", message))

    tracker = Recorder()
    monkeypatch.setattr(_execution, "Progress", lambda *_args, **_kwargs: tracker)

    report = _fusion().evaluate(_benchmark(rubric=True), progress=True)

    assert report.n_scored == 1
    assert len(client.eval_calls) == 4
    assert events == [
        ("stage", "checking", "Checking requirements", None),
        ("stage", "running", "Attempting cases", 1),
        ("advance", "running", 1),
        ("stage", "checking", "Preparing grading", None),
        ("stage", "grading", "Grading responses", 3),
        ("advance", "grading", 3),
        ("stage", "aggregating", "Aggregating report", None),
        ("finish", "Complete"),
    ]


def test_deterministic_grade_and_aggregate_make_no_connection_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "not_connected"},
    )
    run = _fusion().run(_benchmark())
    client.status_reads = 0

    report = run.grade().aggregate()

    assert report.n_scored == 1
    assert client.status_reads == 0


def test_run_stops_unscheduled_cases_after_rejected_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "connected"},
    )
    client.fail_fusion_auth = True

    run = _fusion().run(_benchmark(count=6))

    assert len(client.eval_calls) == 1
    assert len(run.results) == 6
    assert all(result.failure is not None for result in run.results)
    assert run.results[-1].failure is not None
    assert run.results[-1].failure.kind == "skipped"
    assert run.results[-1].failure.code == "not_scheduled"
    assert "not scheduled" in run.results[-1].failure.message
    assert client.status_reads == 2


def test_grade_stops_unscheduled_judge_tasks_after_rejected_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(
        monkeypatch,
        {"codex": "connected", "gemini": "connected", "judge": "connected"},
    )
    run = _fusion().run(_benchmark(rubric=True, count=6))
    client.fail_judge_auth = True
    before = len(client.eval_calls)

    grades = run.grade()

    assert len(client.eval_calls) - before == 16
    assert any("not scheduled" in failure.message for failure in grades.failures)
    auth_failures = [failure for failure in grades.failures if failure.kind == "url4"]
    assert auth_failures
    assert all(failure.code == "connection_needs_reauth" for failure in auth_failures)
    assert client.status_reads == 3
