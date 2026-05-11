from __future__ import annotations

import pytest
from fastapi import APIRouter


@pytest.mark.asyncio
async def test_create_app_fake_anthropic_oauth_factory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIGATEWAY_FAKE_KEYCHAIN", "1")
    monkeypatch.setenv("AIGATEWAY_KEYCHAIN_FILE", str(tmp_path / "keychain.json"))
    monkeypatch.setenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH", "1")

    from aigateway.main import create_app

    app = create_app()
    assert app.state._fake_credential_store is app.state.profile_index._store

    async with app.state.anthropic_http_factory() as client:
        token = await client.post("https://platform.claude.com/oauth/token")
        unmapped = await client.post("https://example.com/oauth/token")

    assert token.status_code == 200
    assert token.json()["access_token"] == "fake-tok"
    assert unmapped.status_code == 404


@pytest.mark.asyncio
async def test_create_app_fake_anthropic_oauth_fail_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AIGATEWAY_FAKE_KEYCHAIN", "1")
    monkeypatch.setenv("AIGATEWAY_KEYCHAIN_FILE", str(tmp_path / "keychain.json"))
    monkeypatch.setenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH", "1")
    monkeypatch.setenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL", "1")

    from aigateway.main import create_app

    app = create_app()

    async with app.state.anthropic_http_factory() as client:
        token = await client.post("https://console.anthropic.com/oauth/token")

    assert token.status_code == 400
    assert token.json() == {"error": "invalid_grant"}


def test_create_app_mounts_provider_auth_router(monkeypatch) -> None:
    from aigateway import main as main_module

    class _Plugin:
        custom_llm_provider = "dummy"

        def register_models(self) -> list:
            return []

        def auth_router(self) -> APIRouter:
            router = APIRouter()

            @router.get("/ping")
            async def ping() -> dict[str, bool]:
                return {"ok": True}

            return router

    def _load_plugins(registry) -> None:
        registry.register(_Plugin())

    monkeypatch.setattr(main_module, "load_plugins", _load_plugins)

    app = main_module.create_app()
    assert any(getattr(route, "path", None) == "/v1/auth/dummy/ping" for route in app.routes)
