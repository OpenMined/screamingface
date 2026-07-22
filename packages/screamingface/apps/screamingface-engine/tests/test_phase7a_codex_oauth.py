from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine import cli
from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings, SettingsError

CODEX_ID = UUID("00000000-0000-0000-0000-000000000007")
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"


@pytest.mark.asyncio
async def test_codex_oauth_uses_registered_engine_callback_and_secret_safe_relay() -> None:
    seen: list[tuple[str, str, dict[str, object] | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/v1/oauth/connections":
            return httpx.Response(200, json={"connections": []})
        if request.url.path == "/v1/oauth/connections":
            assert body == {
                "provider": "codex",
                "label": "default",
                "redirect_uri": CODEX_REDIRECT_URI,
            }
            return httpx.Response(
                201,
                json={
                    "connection_id": str(CODEX_ID),
                    "authorize_url": (
                        "https://auth.openai.example/authorize?"
                        "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback"
                    ),
                    "state": "gateway-state",
                    "expires_in": 600,
                },
            )
        assert request.url.path == "/v1/auth/codex/exchange-code"
        assert body == {"code": "provider-code", "state": "gateway-state"}
        assert request.url.query == b""
        return httpx.Response(200, json={"state": "authenticated"})

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(
        model_routes=MODEL_ROUTES,
        settings=Settings(
            gateway_url="http://gateway.test",
            codex_oauth_redirect_uri=CODEX_REDIRECT_URI,
        ),
        gateway=gateway,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        started = await client.post("/v1/connections/codex/oauth")
        callback = await client.get(
            "/auth/callback",
            params={"code": "provider-code", "state": "gateway-state"},
        )
    await gateway.aclose()

    authorize_query = parse_qs(urlsplit(started.json()["authorize_url"]).query)
    assert authorize_query["redirect_uri"] == [CODEX_REDIRECT_URI]
    assert callback.status_code == 200
    assert seen[-1] == (
        "POST",
        "/v1/auth/codex/exchange-code",
        {"code": "provider-code", "state": "gateway-state"},
    )


def test_codex_redirect_setting_is_validated_at_startup() -> None:
    assert Settings().codex_oauth_redirect_uri == CODEX_REDIRECT_URI
    assert (
        Settings.from_env(
            {"SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI": "http://127.0.0.1:1457/auth/callback"}
        ).codex_oauth_redirect_uri
        == "http://127.0.0.1:1457/auth/callback"
    )

    invalid = (
        "http://localhost:4404/auth/callback",
        "https://localhost:1455/auth/callback",
        "http://example.com:1455/auth/callback",
        "http://localhost:1455/wrong",
        "http://localhost:1455/auth/callback?secret=value",
    )
    for value in invalid:
        with pytest.raises(SettingsError, match="SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI"):
            Settings(codex_oauth_redirect_uri=value)


def test_compose_publishes_the_codex_callback_to_the_engine_listener() -> None:
    compose = (Path(__file__).parents[1] / "compose.yaml").read_text()

    assert '"127.0.0.1:${CODEX_OAUTH_HOST_PORT:-1455}:4404"' in compose
    assert (
        "SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI: "
        "http://localhost:${CODEX_OAUTH_HOST_PORT:-1455}/auth/callback"
    ) in compose


def test_engine_server_does_not_log_oauth_codes_or_url4_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(_app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(cli.importlib, "import_module", lambda _name: SimpleNamespace(run=run))
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda _cls: Settings()))

    cli.main()

    assert captured["access_log"] is False
