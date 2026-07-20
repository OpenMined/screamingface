from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import httpx
import pytest

import screamingface as sf
from screamingface import _execution, connections
from screamingface._profile import Registry


def _fusion() -> sf.Fusion:
    return sf.Fusion(
        "panel",
        models=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )


def _case(index: int) -> sf.Case:
    return sf.Case(f"q{index}", f"Question {index}", reference="A")


def _success() -> httpx.Response:
    return httpx.Response(
        200,
        text=json.dumps(
            {
                "schema": "screamingface.fusion-result.v1",
                "members": {
                    "member_1": {"model": "codex/gpt-5.5", "answer": "A"},
                    "member_2": {"model": "gemini/2.5-flash", "answer": "A"},
                },
                "answer": "A",
            }
        ),
        headers={"content-type": "text/plain"},
        request=httpx.Request("GET", "http://engine.test/v1"),
    )


def _failure(code: str, *, status: int = 502) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"code": code, "message": f"safe {code} failure"}},
        request=httpx.Request("GET", "http://engine.test/v1"),
    )


class _Client:
    def __init__(self, responses: Iterator[httpx.Response]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        assert url == "/v1"
        assert params is not None
        self.calls.append(params["q"])
        return next(self._responses)


def _expressions(count: int) -> tuple[tuple[sf.Case, str], ...]:
    return tuple((_case(index), f"expression-{index}") for index in range(count))


def _registry() -> Registry:
    return Registry((), (), ("screamingface.fusion-result.v1",), 61_440, ())


def test_permanent_canary_failure_stops_every_later_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(iter((_failure("connection_needs_reauth", status=500),)))
    refreshed = 0

    def refresh(_registry: object) -> object:
        nonlocal refreshed
        refreshed += 1
        return object()

    monkeypatch.setattr(connections, "_list_for_registry", refresh)

    results = _execution._execute_cases(client, _fusion(), _expressions(5), _registry())

    assert client.calls == ["expression-0"]
    assert len(results) == 5
    assert results[0].failure is not None
    assert results[0].failure.code == "connection_needs_reauth"
    assert all(result.failure is not None for result in results[1:])
    assert all(result.failure.kind == "skipped" for result in results[1:] if result.failure)
    assert all(result.failure.code == "not_scheduled" for result in results[1:] if result.failure)
    assert all(
        "not scheduled" in result.failure.message for result in results[1:] if result.failure
    )
    assert refreshed == 1


def test_transient_canary_retries_once_then_continues_after_recovery() -> None:
    client = _Client(iter((_failure("provider_unavailable"), _success(), _success(), _success())))

    results = _execution._execute_cases(client, _fusion(), _expressions(3), _registry())

    assert client.calls.count("expression-0") == 2
    assert set(client.calls) == {"expression-0", "expression-1", "expression-2"}
    assert [result.case_id for result in results] == ["q0", "q1", "q2"]
    assert all(result.failure is None for result in results)


def test_repeated_transient_canary_failure_stops_later_cases() -> None:
    client = _Client(iter((_failure("provider_unavailable"), _failure("provider_unavailable"))))

    results = _execution._execute_cases(client, _fusion(), _expressions(5), _registry())

    assert client.calls == ["expression-0", "expression-0"]
    assert len(results) == 5
    assert results[0].failure is not None
    assert results[0].failure.code == "provider_unavailable"
    assert all(result.failure is not None for result in results[1:])
    assert all(result.failure.kind == "skipped" for result in results[1:] if result.failure)
    assert all(result.failure.code == "not_scheduled" for result in results[1:] if result.failure)
    assert all(
        "not scheduled" in result.failure.message for result in results[1:] if result.failure
    )


def test_single_successful_case_is_not_duplicated() -> None:
    client = _Client(iter((_success(),)))

    results = _execution._execute_cases(client, _fusion(), _expressions(1), _registry())

    assert client.calls == ["expression-0"]
    assert len(results) == 1
    assert results[0].failure is None
