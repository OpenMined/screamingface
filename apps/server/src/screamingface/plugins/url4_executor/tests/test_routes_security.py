from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.url4_executor.routes import create_router


class _FakePluginRegistry:
    def __init__(self, active: dict) -> None:
        self.active_plugins = active


class _FakeDispatchPlugin:
    name = "aigw-claude-backend"
    backend_call_paths = ["/claude"]

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    async def handle_backend_call(self, intent: str, *, sources: str = "", app) -> str:
        self.calls.append((intent, sources, app))
        return "ok"


def _client(app: FastAPI) -> TestClient:
    app.include_router(create_router(app=app))
    return TestClient(app)


def test_ensemble_highlight_requires_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    client = _client(FastAPI())

    missing = client.get("/ensemble/highlight", params={"q": "https://example.com"})
    allowed = client.get(
        "/ensemble/highlight",
        params={"q": "https://example.com"},
        headers={"X-SF-Desktop-Secret": "test-secret"},
    )

    assert missing.status_code == 401
    assert allowed.status_code == 200


def test_ensemble_backend_call_requires_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    app = FastAPI()
    plugin = _FakeDispatchPlugin()
    app.state.plugins = _FakePluginRegistry({plugin.name: plugin})
    client = _client(app)

    missing = client.get("/ensemble", params={"q": "/claude()!ping"})
    allowed = client.get(
        "/ensemble",
        params={"q": "/claude()!ping"},
        headers={"X-SF-Desktop-Secret": "test-secret"},
    )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert allowed.text == "ok"
    assert plugin.calls == [("ping", "", app)]
