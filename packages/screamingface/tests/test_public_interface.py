from __future__ import annotations

from typing import Any

import screamingface as sf
import screamingface.report as report
from screamingface import _default_client


def test_public_v1_surface_has_no_legacy_aliases() -> None:
    assert set(sf.__all__) == {
        "AsyncClient",
        "AuthenticationError",
        "Benchmark",
        "BenchmarkInfo",
        "CaseGrade",
        "CaseResult",
        "ModelCapability",
        "ModelDetails",
        "ModelInfo",
        "ModelParameter",
        "ModelParameterSchema",
        "CandidateResult",
        "Check",
        "Client",
        "Connection",
        "ConnectionPanel",
        "OAuthFlow",
        "AsyncOAuthFlow",
        "CoverageWarning",
        "close",
        "configure",
        "connect",
        "connections",
        "disconnect",
        "Evidence",
        "EvidenceProducer",
        "Event",
        "ExecutionError",
        "EngineUnavailableError",
        "EvaluationWarning",
        "evaluate",
        "Failure",
        "Fusion",
        "Leaderboard",
        "LeaderboardBaseline",
        "LeaderboardEntry",
        "LeaderboardError",
        "LeaderboardInfo",
        "LeaderboardScore",
        "MemberResult",
        "Model",
        "OperationInfo",
        "Pipeline",
        "PlanningError",
        "ProviderConnectionError",
        "Recipe",
        "Report",
        "ScreamingFaceError",
        "Usage",
        "Url4",
        "benchmarks",
        "events",
        "leaderboards",
        "models",
    }
    for removed in (
        "config",
        "Plan",
        "Candidate",
        "Operation",
        "plan",
        "run",
        # WHY "Benchmark" left this list: OME-724 reintroduces it deliberately as the
        # rich discovery value (spec 2026-08-03-OME-722) — not the legacy plan-era type.
        "Case",
        "StudyReport",
        "Grader",
        "Aggregator",
        "EvaluationPlan",
        "PlannedCandidate",
        "PlannedOperation",
        "CandidateReport",
        "MemberReport",
        "Reducer",
        "reducers",
    ):
        assert not hasattr(sf, removed)
    assert sf.models.__all__ == ["get", "list"]
    assert sf.benchmarks.__all__ == ["get", "list"]
    assert sf.leaderboards.__all__ == ["get", "get_score", "list", "submit"]
    assert sf.connections.__all__ == [
        "AsyncOAuthFlow",
        "Connection",
        "ConnectionStatus",
        "OAuthFlow",
        "get",
        "list",
    ]
    assert report.__all__ == [
        "CaseGrade",
        "CaseResult",
        "CandidateResult",
        "Check",
        "Evidence",
        "EvidenceProducer",
        "Failure",
        "MemberResult",
        "OperationInfo",
        "Report",
        "Usage",
    ]


def test_module_evaluate_delegates_to_the_lazy_default_client(monkeypatch: Any) -> None:
    sentinel = object()
    calls: list[tuple[object, str | None, int | None]] = []

    class FakeClient:
        def evaluate(
            self,
            candidates: object,
            *,
            benchmark: str | None = None,
            limit: int | None = None,
            **_: object,
        ) -> object:
            calls.append((candidates, benchmark, limit))
            return sentinel

    monkeypatch.setattr(_default_client, "default_client", lambda: FakeClient())

    candidates = sf.Model("provider/model")
    result = sf.evaluate(candidates, benchmark="draco", limit=1)

    assert result is sentinel
    assert calls == [(candidates, "draco", 1)]

    result = sf.evaluate("(candidate:0.0:'recipe')!'done'", progress=False)

    assert result is sentinel
    assert calls[-1] == ("(candidate:0.0:'recipe')!'done'", None, None)


def test_default_client_is_lazy_and_reads_environment_once(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(_default_client, "_client", None)
    monkeypatch.setenv("SCREAMINGFACE_ENGINE_URL", "https://first.example")

    first = _default_client.default_client()
    monkeypatch.setenv("SCREAMINGFACE_ENGINE_URL", "https://second.example")
    second = _default_client.default_client()

    assert first is second
    assert first.engine_url == "https://first.example"
    first.close()
    monkeypatch.setattr(_default_client, "_client", None)


def test_default_client_lazily_selects_the_hosted_engine_without_an_override(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(_default_client, "_client", None)
    monkeypatch.delenv("SCREAMINGFACE_ENGINE_URL", raising=False)

    client = _default_client.default_client()

    assert client.engine_url == "https://fusion.dev.screamingface.ai"
    client.close()
    monkeypatch.setattr(_default_client, "_client", None)


def test_default_client_can_be_reconfigured_and_closed() -> None:
    _default_client.close()
    first = sf.configure(
        engine_url="https://first.example",
        scoreboard_url="https://first-scoreboard.example",
    )

    second = sf.configure(
        engine_url="https://second.example",
        scoreboard_url="https://second-scoreboard.example",
    )

    assert first.closed is True
    assert second is _default_client.default_client()
    assert second.engine_url == "https://second.example"
    assert second.scoreboard_url == "https://second-scoreboard.example"

    sf.close()

    assert second.closed is True
    assert _default_client._client is None


def test_operation_info_is_a_constructible_public_report_value() -> None:
    operation = sf.OperationInfo(
        id="op_answer",
        kind="model",
        label="answer",
        depends_on=(),
    )

    assert operation.depends_on == ()
    assert not hasattr(sf, "Operation")
