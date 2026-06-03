from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings
from screamingface.plugins.claude_backend_api.routes import create_router as create_claude_router
from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiSettings
from screamingface.plugins.codex_backend_api.routes import create_router as create_codex_router
from screamingface.plugins.gemini_backend_api.auth import GeminiAuth
from screamingface.plugins.gemini_backend_api.plugin import GeminiBackendApiSettings
from screamingface.plugins.gemini_backend_api.routes import create_router as create_gemini_router
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource


def _external_app() -> SimpleNamespace:
    app = SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": "external",
                        "gateway_url": "http://aigw.test",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )
    from screamingface.plugins.aigw_base.client import gateway_session_state

    gateway_session_state(app).set_token("gateway-jwt", datetime.now(UTC) + timedelta(minutes=5))
    return app


def _find_backend(value: Any, seen: set[int] | None = None) -> Any:
    seen = seen or set()
    if id(value) in seen:
        return None
    seen.add(id(value))
    if hasattr(value, "_auth"):
        return value
    backend = getattr(value, "backend", None)
    if backend is not None and hasattr(backend, "_auth"):
        return backend
    closure = getattr(value, "__closure__", None)
    if closure:
        for cell in closure:
            try:
                found = _find_backend(cell.cell_contents, seen)
            except ValueError:
                continue
            if found is not None:
                return found
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "router_factory", "settings", "auth_cls", "expected_header"),
    [
        (
            "claude",
            create_claude_router,
            ClaudeBackendApiSettings(connection_id="conn-1", aigw_url="http://aigw.test"),
            ClaudeCodeOAuth,
            "Bearer route-token",
        ),
        (
            "codex",
            create_codex_router,
            CodexBackendApiSettings(connection_id="conn-1", aigw_url="http://aigw.test"),
            CodexOAuth,
            "Bearer route-token",
        ),
        (
            "gemini",
            create_gemini_router,
            GeminiBackendApiSettings(connection_id="conn-1", aigw_url="http://aigw.test"),
            GeminiAuth,
            "Bearer route-token",
        ),
    ],
)
async def test_direct_route_backends_use_aigw_source_instead_of_local_credentials(
    monkeypatch,
    name: str,
    router_factory,
    settings,
    auth_cls,
    expected_header: str,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_local_read(self):  # noqa: ANN001
        raise AssertionError("local credential path must not be reached")

    async def fetch_token(self: AigwTokenSource) -> str:  # noqa: ARG001
        return "route-token"

    monkeypatch.setattr(auth_cls, "_read_credential", fail_local_read)
    monkeypatch.setattr(AigwTokenSource, "fetch_token", fetch_token)

    router = router_factory(settings, app=_external_app())
    for path in (f"/{name}/run", f"/{name}"):
        route = next(route for route in router.routes if route.path == path)
        backend = _find_backend(route.endpoint)
        assert backend is not None
        assert backend._auth._aigw_source is not None
        assert backend._auth._aigw_source.connection_id == "conn-1"
        headers = await backend._auth.get_authorization_header()
        assert headers["Authorization"] == expected_header
