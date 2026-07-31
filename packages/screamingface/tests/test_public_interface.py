from __future__ import annotations

from typing import Any

import screamingface as sf
import screamingface.report as report
from screamingface import _default_client


def test_public_v1_surface_has_no_legacy_aliases() -> None:
    assert set(sf.__all__) == {
        "AsyncClient",
        "AuthenticationError",
        "BenchmarkInfo",
        "ModelInfo",
        "CandidateResult",
        "Client",
        "Connection",
        "ConnectionPanel",
        "connect",
        "connections",
        "disconnect",
        "Event",
        "ExecutionError",
        "evaluate",
        "Failure",
        "Fusion",
        "MemberResult",
        "Model",
        "PlanningError",
        "ProviderConnectionError",
        "Recipe",
        "Report",
        "ScreamingFaceError",
        "Usage",
        "benchmarks",
        "events",
        "models",
    }
    for removed in (
        "config",
        "Plan",
        "Candidate",
        "Operation",
        "plan",
        "run",
        "Benchmark",
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
    assert sf.models.__all__ == ["list"]
    assert sf.benchmarks.__all__ == ["list"]
    assert sf.connections.__all__ == ["Connection", "ConnectionStatus", "get", "list"]
    assert report.__all__ == [
        "CandidateResult",
        "Failure",
        "MemberResult",
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

    candidates = object()
    result = sf.evaluate(candidates, limit=1)  # type: ignore[arg-type]

    assert result is sentinel
    assert calls == [(candidates, None, 1)]


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
