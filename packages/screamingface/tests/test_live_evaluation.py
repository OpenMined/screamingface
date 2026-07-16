from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import screamingface as sf
import screamingface.evaluation as evaluation
import screamingface.session as session_module
from screamingface.data import Question
from screamingface.gateway import Completion, Connection, ProviderCapability


@dataclass
class FakeGateway:
    calls: int = 0
    connections: list[Connection] = field(default_factory=list)

    async def list_models(self) -> list[str]:
        return [
            "codex/gpt-5.5",
            "gemini-cli/gemini-2.5-pro",
            "anthropic/claude-sonnet-4-6",
        ]

    async def list_connections(self) -> list[Connection]:
        return list(self.connections)

    async def list_providers(self) -> list[ProviderCapability]:
        return []

    async def get_connection(self, connection_id: str) -> Connection:
        return Connection(connection_id, "codex", "default", "active")

    async def create_api_key_connection(
        self, provider: str, label: str | None, api_key: str
    ) -> Connection:
        del api_key
        return Connection("keyed", provider, label or "default", "active", "api_key")

    async def replace_api_key_connection(self, connection_id: str, api_key: str) -> Connection:
        del api_key
        return Connection(connection_id, "codex", "default", "active", "api_key")

    async def delete_connection(self, connection_id: str) -> None:
        del connection_id

    async def aclose(self) -> None:
        return None

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Completion:
        del model, messages, profile, max_tokens, temperature
        self.calls += 1
        return Completion("A", prompt_tokens=20, completion_tokens=1, total_tokens=21)


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _questions(_first: int, _seed: int) -> tuple[Question, ...]:
    return (
        Question("live-1", "physics", "Synthetic transport test?", ("Yes", "No"), 0),
        Question("live-2", "biology", "Another transport test?", ("Yes", "No"), 0),
    )


def test_live_evaluation_uses_gateway_and_reports_live_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeGateway(
        connections=[
            Connection("codex", "codex", "default", "active", "oauth"),
            Connection("gemini", "gemini-cli", "default", "active", "oauth"),
            Connection("anthropic", "anthropic", "default", "active", "oauth"),
        ]
    )
    session = sf.Session(
        mode="live",
        gateway_url="https://gateway.example",
        gateway=gateway,
    )
    monkeypatch.setattr(session_module, "_active", session)
    monkeypatch.setattr(evaluation, "load_live_questions", _questions)
    ids = sf.models.list(max_price=20)
    fusion = sf.Fusion("live", ids[:3], judge=ids[0])

    run = fusion.evaluate("gpqa", first=2, seed=0)

    assert run.mode == "live"
    assert run.benchmark == "GPQA Diamond"
    assert run.dataset_source == "gated:Idavidrein/gpqa:gpqa_diamond"
    assert run.sample_size == 2
    assert run.cost_usd > 0
    assert gateway.calls == 6


def test_model_discovery_lists_only_actively_connected_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: spec §5 — live discovery mirrors the setup panel: only models whose
    # provider holds an ACTIVE gateway connection are listed, re-read on every call so
    # a provider connected through the widget appears without a new setup.
    gateway = FakeGateway()
    session = sf.Session(
        mode="live",
        gateway_url="https://gateway.example",
        gateway=gateway,
        connected_providers=frozenset(),
    )
    monkeypatch.setattr(session_module, "_active", session)

    assert sf.models.list() == []

    gateway.connections.append(Connection("anthropic", "anthropic", "default", "active", "oauth"))
    gateway.connections.append(Connection("codex", "codex", "default", "pending", "oauth"))
    assert sf.models.list() == ["anthropic/claude-sonnet-4-6"]

    gateway.connections.append(Connection("codex-2", "codex", "default", "active", "oauth"))
    assert sf.models.list() == ["codex/gpt-5.5", "anthropic/claude-sonnet-4-6"]


def test_evaluation_preflight_aggregates_missing_providers_without_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeGateway()
    session = sf.Session(
        mode="live",
        gateway_url="https://gateway.example",
        gateway=gateway,
        connected_providers=frozenset(),
    )
    monkeypatch.setattr(session_module, "_active", session)
    monkeypatch.setattr(
        evaluation,
        "load_live_questions",
        lambda _first, _seed: pytest.fail("dataset must not load before preflight"),
    )
    monkeypatch.setattr(
        evaluation,
        "_progress_reporter",
        lambda *_args: pytest.fail("progress must not render before preflight"),
    )
    # Explicit SDK-catalog IDs: with no active connections, sf.models.list() is
    # empty by design, yet composition must still work for known models.
    ids = (
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    )
    fusion = sf.Fusion("blocked", ids, judge=ids[0])

    with pytest.raises(sf.FusionNotReady) as caught:
        fusion.evaluate("gpqa", first=2)

    message = str(caught.value)
    assert caught.value.missing_providers == ("anthropic", "codex", "gemini-cli")
    assert "anthropic/claude-sonnet-4-6" in message
    assert "codex/gpt-5.5" in message
    assert "No benchmark data was loaded and no model calls were made" in message
    compact = caught.value._render_traceback_()
    assert compact == [f"FusionNotReady: {message}"]
    assert "evaluation.py" not in compact[0]
    assert gateway.calls == 0


def test_evaluation_preflight_reports_gateway_unavailable_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingModelGateway(FakeGateway):
        async def list_models(self) -> list[str]:
            return ["codex/gpt-5.5", "gemini-cli/gemini-2.5-pro"]

    gateway = MissingModelGateway(
        connections=[
            Connection("codex", "codex", "default", "active", "oauth"),
            Connection("gemini", "gemini-cli", "default", "active", "oauth"),
            Connection("anthropic", "anthropic", "default", "active", "oauth"),
        ]
    )
    session = sf.Session(mode="live", gateway_url="https://gateway.example", gateway=gateway)
    monkeypatch.setattr(session_module, "_active", session)
    ids = (
        "codex/gpt-5.5",
        "gemini-cli/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-6",
    )
    fusion = sf.Fusion("missing-model", ids, judge=ids[0])

    with pytest.raises(sf.FusionNotReady) as caught:
        fusion.evaluate("gpqa", first=1)

    assert caught.value.missing_providers == ()
    assert caught.value.unavailable_models == ("anthropic/claude-sonnet-4-6",)
    assert "not available from AI Gateway" in str(caught.value)
    assert gateway.calls == 0
