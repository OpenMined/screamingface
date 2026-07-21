from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest

import screamingface as sf
from screamingface import _profile, connections
from screamingface._profile import ProviderRecord
from screamingface._requirements import evaluate_requirements, grade_requirements, run_requirements
from screamingface.connections import ConnectionStatus, OAuthFlow


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [
            {"id": "codex", "display_name": "OpenAI Codex", "auth_methods": ["oauth"]},
            {
                "id": "gemini",
                "display_name": "Google Gemini",
                "auth_methods": ["oauth", "api_key"],
            },
        ],
        "models": [
            {"id": "codex/gpt-5.5", "provider": "codex", "supported_tools": []},
            {"id": "gemini/2.5-flash", "provider": "gemini", "supported_tools": []},
        ],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote"}],
    }


def _connection(provider: str, status: str = "not_connected") -> dict[str, object]:
    return {
        "provider": provider,
        "status": status,
        "auth_method": "oauth" if status == "connected" else None,
        "account_label": "researcher@example.com" if status == "connected" else None,
    }


def _response(  # noqa: PLR0911 - explicit fake-engine route table
    request: httpx.Request, calls: list[tuple[str, str, bytes]]
) -> httpx.Response:
    body = request.read()
    calls.append((request.method, str(request.url), body))
    if request.url.path == "/.well-known/screamingface":
        return httpx.Response(200, json=_registry())
    if request.url.path == "/v1/connections" and request.method == "GET":
        return httpx.Response(
            200,
            json={
                "schema": "screamingface.connections.v1",
                "connections": [_connection("codex", "connected"), _connection("gemini")],
            },
        )
    if request.url.path == "/v1/connections/gemini/api-key":
        return httpx.Response(200, json=_connection("gemini", "connected"))
    if request.url.path == "/v1/connections/codex/oauth":
        return httpx.Response(
            200,
            json={
                "provider": "codex",
                "status": "pending",
                "authorize_url": "https://auth.example/authorize",
                "expires_in": 30,
            },
        )
    if request.url.path == "/v1/connections/codex" and request.method == "GET":
        return httpx.Response(200, json=_connection("codex", "connected"))
    if request.url.path == "/v1/connections/gemini" and request.method == "GET":
        return httpx.Response(200, json=_connection("gemini"))
    if request.url.path.startswith("/v1/connections/") and request.method == "DELETE":
        return httpx.Response(204)
    return httpx.Response(404)


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, bytes]]:
    calls: list[tuple[str, str, bytes]] = []
    transport = httpx.MockTransport(lambda request: _response(request, calls))
    monkeypatch.setattr(_profile.httpx, "get", httpx.Client(transport=transport).get)
    monkeypatch.setattr("screamingface.connections._transport", transport)
    sf.config(engine="http://127.0.0.1:4404")
    return calls


def test_registry_exposes_public_providers_and_explicit_model_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))

    registry = _profile.load_registry()

    assert registry.providers[1].auth_methods == ("oauth", "api_key")
    assert registry.models[0].provider == "codex"
    assert sf.models.list() == ["codex/gpt-5.5", "gemini/2.5-flash"]


def test_registry_rejects_unknown_model_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _registry()
    models = cast(list[dict[str, object]], payload["models"])
    models[0]["provider"] = "private-gateway-alias"
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(payload))

    with pytest.raises(sf.EngineProfileError, match="unknown provider"):
        _profile.load_registry()


def test_connections_are_immutable_fresh_and_capability_enriched(fake_engine) -> None:
    first = sf.connections.list()
    panel = sf.connect()

    assert first == panel.connections
    assert first[0] == sf.Connection(
        provider="codex",
        display_name="OpenAI Codex",
        auth_methods=("oauth",),
        status="connected",
        auth_method="oauth",
        account_label="researcher@example.com",
    )
    with pytest.raises(AttributeError):
        setattr(first[0], "status", "error")
    assert sum(path.endswith("/v1/connections") for _, path, _ in fake_engine) == 2


def test_connect_api_key_is_only_in_put_json_body(fake_engine) -> None:
    secret = "super-secret-api-key"

    connection = sf.connect("gemini", api_key=secret)

    method, url, body = fake_engine[-1]
    assert connection.status == "connected"
    assert method == "PUT"
    assert secret not in url
    assert json.loads(body) == {"api_key": secret}
    assert secret not in repr(connection)


def test_connect_oauth_returns_origin_scoped_bounded_flow(fake_engine) -> None:
    flow = sf.connect("codex", method="oauth")

    assert isinstance(flow, sf.OAuthFlow)
    assert flow.status == "pending"
    assert flow.authorize_url == "https://auth.example/authorize"
    sf.config(engine="https://different.example")
    assert flow.wait(poll_interval=0) == sf.Connection(
        provider="codex",
        display_name="OpenAI Codex",
        auth_methods=("oauth",),
        status="connected",
        auth_method="oauth",
        account_label="researcher@example.com",
    )
    assert fake_engine[-1][1].startswith("http://127.0.0.1:4404/")
    flow.cancel()
    flow.cancel()


def test_ambiguous_method_and_insecure_private_origin_are_rejected(fake_engine) -> None:
    with pytest.raises(sf.AuthMethodRequiredError, match="oauth.*api_key"):
        sf.connect("gemini")

    sf.config(engine="http://engine.example")
    with pytest.raises(sf.SecureTransportRequiredError, match="HTTPS"):
        sf.connections.list()


def test_disconnect_is_idempotent_and_errors_are_sanitized(fake_engine) -> None:
    assert sf.disconnect("gemini").status == "not_connected"
    assert sf.disconnect("gemini").status == "not_connected"


def test_public_values_and_connection_arguments_are_strict(fake_engine) -> None:
    with pytest.raises(ValueError, match="unknown connection status"):
        sf.Connection("codex", "Codex", ("oauth",), cast(ConnectionStatus, "invalid"), None, None)
    with pytest.raises(ValueError, match="not advertised"):
        sf.Connection("codex", "Codex", ("oauth",), "connected", "api_key", None)
    invalid_connect = cast(Any, sf.connect)
    with pytest.raises(TypeError, match="provider is required"):
        invalid_connect(method="oauth")
    with pytest.raises(ValueError, match="api_key is required"):
        invalid_connect("gemini", method="api_key")
    with pytest.raises(ValueError, match="combined with OAuth"):
        invalid_connect("gemini", method="oauth", api_key="secret")
    with pytest.raises(ValueError, match="non-empty"):
        sf.connect("gemini", api_key=" ")
    with pytest.raises(ValueError, match="provider must"):
        sf.connect("")
    with pytest.raises(sf.UnknownProviderError, match="missing"):
        sf.connect("missing")
    with pytest.raises(sf.UnsupportedAuthMethodError, match="does not support"):
        sf.connect("codex", api_key="secret")


def test_unbound_oauth_flow_and_poll_interval_are_strict(fake_engine) -> None:
    unbound = sf.OAuthFlow(provider="codex", authorize_url="https://auth.example")
    with pytest.raises(ValueError, match="created by sf.connect"):
        unbound.wait()

    flow = sf.connect("codex", method="oauth")
    with pytest.raises(TypeError, match="poll_interval"):
        flow.wait(poll_interval=cast(float, True))
    with pytest.raises(ValueError, match="poll_interval"):
        flow.wait(poll_interval=-1)


def test_oauth_wait_expires_without_an_unbounded_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ProviderRecord("codex", "OpenAI Codex", ("oauth",))
    flow = OAuthFlow(
        provider="codex",
        authorize_url="https://auth.example",
        _engine_url="http://127.0.0.1:4404",
        _provider_record=provider,
        _expires_at=0,
    )
    monkeypatch.setattr(connections.time, "monotonic", lambda: 1.0)
    monkeypatch.setattr(
        connections,
        "_get_connection",
        lambda *_args, **_kwargs: pytest.fail("expired flow polled the engine"),
    )

    with pytest.raises(sf.ProviderConnectionError) as failure:
        flow.wait(poll_interval=0)
    assert failure.value.code == "connection_pending"


@pytest.mark.parametrize(
    "status", ["not_connected", "pending", "connected", "needs_reauth", "error"]
)
def test_all_connection_statuses_are_public_values(status: str) -> None:
    value = sf.Connection(
        "codex",
        "OpenAI Codex",
        ("oauth",),
        cast(ConnectionStatus, status),
        "oauth" if status == "connected" else None,
        None,
    )

    assert value.status == status


def test_private_transport_rejects_redirects_and_unsafe_error_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sf.config(engine="http://127.0.0.1:4404")
    monkeypatch.setattr(
        connections,
        "_transport",
        httpx.MockTransport(lambda _request: httpx.Response(307, headers={"location": "/leak"})),
    )
    with pytest.raises(sf.EngineProtocolError, match="must not redirect"):
        connections._request("GET", "/v1/connections")

    monkeypatch.setattr(
        connections,
        "_transport",
        httpx.MockTransport(lambda _request: httpx.Response(502, text="upstream secret body")),
    )
    with pytest.raises(sf.EngineProtocolError) as malformed:
        connections._request("GET", "/v1/connections")
    assert "upstream secret body" not in str(malformed.value)


def test_private_transport_decodes_only_the_safe_error_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "schema": "screamingface.error.v1",
        "code": "gateway_timeout",
        "message": "The provider gateway timed out.",
        "provider": "gemini",
        "retryable": True,
    }
    monkeypatch.setattr(
        connections,
        "_transport",
        httpx.MockTransport(lambda _request: httpx.Response(504, json=payload)),
    )
    sf.config(engine="http://127.0.0.1:4404")

    with pytest.raises(sf.ProviderConnectionError) as failure:
        connections._request("GET", "/v1/connections")
    assert failure.value.code == "gateway_timeout"
    assert failure.value.provider == "gemini"
    assert failure.value.retryable is True


def test_malformed_connection_lists_always_raise_a_typed_protocol_error() -> None:
    provider = ProviderRecord("codex", "OpenAI Codex", ("oauth",))

    with pytest.raises(sf.EngineProtocolError, match="invalid connections response"):
        connections._decode_connection_list(
            {"schema": "screamingface.connections.v1", "connections": [], "extra": True},
            (provider,),
        )


def test_stage_requirement_planning_uses_explicit_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))
    registry = _profile.load_registry()
    fusion = sf.Fusion(
        "panel",
        inputs=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.Model(
            model="codex/gpt-5.5",
            prompt="Reduce: $panel_answers",
        ),
    )
    benchmark = sf.Benchmark(
        "judged@1",
        cases=[sf.Case("one", "Question", reference={"criteria": []})],
        grader=sf.graders.Rubric(model="gemini/2.5-flash", prompt="Judge: $answer"),
    )

    assert [
        (item.provider, item.role) for item in run_requirements(fusion, benchmark, registry)
    ] == [
        ("codex", "member"),
        ("gemini", "member"),
        ("codex", "reducer"),
    ]
    assert [(item.provider, item.role) for item in grade_requirements(benchmark, registry)] == [
        ("gemini", "grader")
    ]
    assert len(evaluate_requirements(fusion, benchmark, registry)) == 4


def test_deterministic_strategies_add_no_model_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))
    registry = _profile.load_registry()
    fusion = sf.Fusion(
        "vote",
        inputs=["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )
    benchmark = sf.Benchmark(
        "choices@1",
        cases=[sf.Case("one", "Question", reference="A")],
        grader=sf.graders.ExactChoice(),
    )

    assert [item.role for item in run_requirements(fusion, benchmark, registry)] == [
        "member",
        "member",
    ]
    assert grade_requirements(benchmark, registry) == ()

    repeated = sf.Fusion(
        "repeated",
        inputs=["codex/gpt-5.5", "codex/gpt-5.5"],
        reducer=sf.reducers.MajorityVote(),
    )
    repeated_requirements = run_requirements(repeated, benchmark, registry)
    assert repeated_requirements == (repeated_requirements[0],)
