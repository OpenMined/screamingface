from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import screamingface as sf
import screamingface.evaluation as evaluation
import screamingface.session as session_module
from screamingface.data import Question
from screamingface.errors import ProviderCallError
from screamingface.gateway import Completion, Connection, ProviderCapability


@dataclass
class ProductionGateway:
    closed: bool = False
    api_keys_seen: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    async def list_models(self) -> list[str]:
        return ["codex/gpt-5.5", "anthropic/claude-sonnet-4-6"]

    async def list_connections(self) -> list[Connection]:
        return [
            Connection("conn-1", "codex", "work", "active", "oauth"),
            Connection("conn-2", "anthropic", "claude", "active", "oauth"),
        ]

    async def list_providers(self) -> list[ProviderCapability]:
        return [ProviderCapability("anthropic", ("api_key", "oauth"), 2)]

    async def get_connection(self, connection_id: str) -> Connection:
        return Connection(connection_id, "codex", "work", "active", "oauth")

    async def create_api_key_connection(
        self, provider: str, label: str | None, api_key: str
    ) -> Connection:
        self.api_keys_seen.append(api_key)
        return Connection("key-1", provider, label or "default", "active", "api_key")

    async def replace_api_key_connection(self, connection_id: str, api_key: str) -> Connection:
        self.api_keys_seen.append(api_key)
        return Connection(connection_id, "anthropic", "default", "active", "api_key")

    async def delete_connection(self, connection_id: str) -> None:
        self.deleted.append(connection_id)

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Completion:
        del messages, profile, max_tokens, temperature
        if model.startswith("anthropic/"):
            raise ProviderCallError(model, "provider_unavailable", "Provider is not ready")
        return Completion("A", prompt_tokens=12, completion_tokens=1, total_tokens=13)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _live_session(gateway: ProductionGateway) -> sf.Session:
    session = sf.Session(
        mode="live",
        gateway_url="https://gateway.test",
        profiles={"codex": "work", "anthropic": "claude"},
        connected_providers=frozenset({"codex", "anthropic"}),
        gateway=gateway,
    )
    session_module._active = session
    return session


def test_public_connection_operations_are_secret_safe() -> None:
    gateway = ProductionGateway()
    session = _live_session(gateway)

    assert session.connections()[0].label == "work"
    key = "sk-private-provider-key"
    connection = session.connect("anthropic", api_key=key)
    assert isinstance(connection, Connection)
    assert connection.auth_type == "api_key"
    assert key not in repr(connection)
    assert not hasattr(session, "api_key")
    assert session.wait_for_connection("pending-1", timeout_s=0.1).status == "active"
    session.disconnect("key-1")
    assert gateway.deleted == ["key-1"]


def test_partial_provider_failure_preserves_answers_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = ProductionGateway()
    _live_session(gateway)
    question = Question("live-1", "science", "Oxygen symbol?", ("O", "N", "C", "H"), 0)
    monkeypatch.setattr(evaluation, "load_live_questions", lambda _first, _seed: (question,))
    ids = ["codex/gpt-5.5", "anthropic/claude-sonnet-4-6"]

    run = sf.Fusion("resilient", ids, judge=ids[0]).evaluate("gpqa", first=1)

    assert run.score == 100
    assert run.incomplete == 1
    assert run.failures[0].code == "provider_unavailable"
    assert run.failures[0].model == "anthropic/claude-sonnet-4-6"
    assert run.profiles == (("anthropic", "claude"), ("codex", "work"))
    assert run.total_tokens == 13
    assert run.model_results[0].model == "codex/gpt-5.5"
    assert run.pricing_source
    assert run.pricing_as_of


def test_reset_closes_live_client_and_runtime_remains_reusable() -> None:
    gateway = ProductionGateway()
    _live_session(gateway)

    sf.reset_session()

    assert gateway.closed is True
    assert sf.current_session() is None
    assert sf.setup(mode="mock").mode == "mock"
    sf.shutdown()
    assert sf.setup(mode="mock").mode == "mock"


def test_model_pricing_metadata_is_explicit_and_dated() -> None:
    sf.setup(mode="mock")
    model = sf.models.get("codex/gpt-5.5")

    assert model.price_per_million is not None
    assert model.pricing_source.startswith("estimate:")
    assert model.pricing_as_of.isoformat() == "2026-07-16"
    assert model.pricing_basis == "blended_tokens"


def test_module_connection_facade_and_closed_session_errors() -> None:
    gateway = ProductionGateway()
    session = _live_session(gateway)
    assert sf.connections()[0].id == "conn-1"
    connected = sf.connect("anthropic", api_key="one-shot")
    assert connected.id == "key-1"
    assert sf.wait_for_connection("conn-1", timeout_s=0.1).status == "active"
    sf.disconnect("conn-1")
    session.close()
    with pytest.raises(sf.GatewayError, match="live, open"):
        session.connections()


@pytest.mark.asyncio
async def test_connection_wait_terminal_and_timeout() -> None:
    class EndingGateway(ProductionGateway):
        status = "error"

        async def get_connection(self, connection_id: str) -> Connection:
            return Connection(connection_id, "codex", "work", self.status)

    gateway = EndingGateway()
    with pytest.raises(sf.GatewayError, match="ended"):
        await session_module._wait_for_connection(gateway, "one", 0.1)
    gateway.status = "pending"
    with pytest.raises(sf.GatewayError, match="Timed out"):
        await session_module._wait_for_connection(gateway, "one", 0.001)
    with pytest.raises(ValueError, match="positive"):
        await session_module._wait_for_connection(gateway, "one", 0)
