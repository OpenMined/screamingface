"""Tests for URL4 profile-alias dispatch on ``BackendApiPluginBase`` (SF-346).

``handle_backend_alias`` is the profile-capable seam the URL4 dispatcher calls
for ``/<backend>/<alias>(...)`` expressions. It validates the alias (reusing the
same ``_PROFILE_NAME_RE`` that guards profile-config keys), then executes the
profile through the shared ``execute_profile_text`` helper — so the alias runs
the profile's model, never the backend default.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from screamingface.core.classes import ClassRegistry
from screamingface.core.config import AppConfig, ServerConfig
from screamingface.core.hooks import HookRegistry
from screamingface.core.routes import RouteRegistry
from screamingface.plugins.backend_api_base.models import BackendProfile
from screamingface.plugins.backend_api_base.plugin_base import BackendApiPluginBase
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition, extract_text
from screamingface.plugins.llm_base.routes_shared import BackendApiConfig, build_backend_api_router

# handle_backend_alias ignores its ``app`` argument (it delegates through the
# captured config), so a bare app satisfies the type without any wiring.
_APP = FastAPI()


class _RecordingBackend(Backend):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        self.calls.append({"model": model, "prompt": extract_text(messages[0]) if messages else ""})
        return CoreMessage(role="assistant", content=f"ran {model}")


class _AliasPlugin(BackendApiPluginBase):
    name = "alias-test-backend-api"
    backend_call_paths = ["/aliastest"]
    schema_link_base = "/aliastest/"


def _cfg(backend: Backend, profiles: dict[str, BackendProfile]) -> BackendApiConfig:
    settings = SimpleNamespace(default_model=None, timeout_seconds=300.0, profiles=profiles)
    return BackendApiConfig(
        name="alias-test-backend-api",
        path_prefix="/aliastest",
        default_model="provider/hardcoded-default",
        backend=backend,
        settings=settings,
        app=None,
        build_interpreter=lambda: None,
        span_prefix="aliastest",
    )


def _make_plugin(backend: Backend, profiles: dict[str, BackendProfile]) -> _AliasPlugin:
    plugin = _AliasPlugin()
    plugin.settings = SimpleNamespace(  # type: ignore[assignment]
        default_model=None, timeout_seconds=300.0, profiles=profiles
    )
    plugin._api_config = _cfg(backend, profiles)
    return plugin


def test_backend_api_base_supports_profile_aliases_by_default() -> None:
    assert BackendApiPluginBase.supports_profile_aliases is True


@pytest.mark.asyncio
async def test_handle_backend_alias_runs_the_profile_model() -> None:
    backend = _RecordingBackend()
    profiles = {"oss20b": BackendProfile(model="huggingface/openai/gpt-oss-20b:cheapest")}
    plugin = _make_plugin(backend, profiles)

    out = await plugin.handle_backend_alias("oss20b", sources="", intent="answer", app=_APP)

    assert backend.calls[0]["model"] == "huggingface/openai/gpt-oss-20b:cheapest"
    assert "gpt-oss-20b" in out


@pytest.mark.asyncio
async def test_handle_backend_alias_rejects_invalid_syntax() -> None:
    backend = _RecordingBackend()
    profiles = {"oss20b": BackendProfile(model="m/x")}
    plugin = _make_plugin(backend, profiles)

    with pytest.raises(Exception, match="Invalid profile alias 'OSS20b'"):
        await plugin.handle_backend_alias("OSS20b", sources="", intent="q", app=_APP)
    assert backend.calls == []


@pytest.mark.asyncio
async def test_handle_backend_alias_unknown_alias_names_the_backend() -> None:
    backend = _RecordingBackend()
    profiles = {"oss20b": BackendProfile(model="m/x")}
    plugin = _make_plugin(backend, profiles)

    with pytest.raises(
        Exception, match="No profile alias 'nope' is configured for backend /aliastest"
    ):
        await plugin.handle_backend_alias("nope", sources="", intent="q", app=_APP)
    assert backend.calls == []


def test_setup_captures_api_config_from_router() -> None:
    backend = _RecordingBackend()
    profiles = {"oss20b": BackendProfile(model="m/x")}
    cfg = _cfg(backend, profiles)

    class _P(BackendApiPluginBase):
        name = "alias-test-backend-api"
        backend_call_paths = ["/aliastest"]
        create_router = staticmethod(lambda settings, app=None: build_backend_api_router(cfg))

    plugin = _P()
    plugin.settings = cfg.settings  # type: ignore[assignment]

    app = FastAPI()
    app.state.config = AppConfig(server=ServerConfig(host="127.0.0.1"))
    plugin.setup(app=app, hooks=HookRegistry(), classes=ClassRegistry(), routes=RouteRegistry(app))

    assert plugin._api_config is cfg
