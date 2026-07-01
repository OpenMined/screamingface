"""URL4 profile-alias dispatch in ``_dispatch_backend_call`` (SF-346).

``/backend/<alias>(ctx)!intent`` resolves — only after an exact-path miss — to a
configured profile on a profile-capable plugin, executed via the model-aware
shared path. These tests pin: exact-match precedence, alias routing, single-
segment enforcement, the ``/python`` (non-profile) guard, unchanged unknown-
backend behavior, the ensemble/collection reducer path, and — most importantly —
that the profile's *model* actually reaches ``backend.run()``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from screamingface.plugin import Plugin
from screamingface.plugins.backend_api_base.models import BackendProfile
from screamingface.plugins.backend_api_base.plugin_base import BackendApiPluginBase
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition, extract_text
from screamingface.plugins.llm_base.routes_shared import BackendApiConfig
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import Url4BackendCall, Url4Text
from screamingface.plugins.url4_executor.url4_resolve import (
    _dispatch_backend_call,
    _dispatch_backend_call_with_intent,
)


class _Registry:
    def __init__(self, plugins: dict) -> None:
        self.active_plugins = plugins


def _app(plugins: dict) -> FastAPI:
    app = FastAPI()
    app.state.plugins = _Registry(plugins)
    return app


class _SpyBackendPlugin(Plugin):
    """Records which dispatch method fired without doing real work."""

    name = "spy"
    backend_call_paths = ["/spy"]
    supports_profile_aliases = True

    def __init__(self) -> None:
        self.exact_called = False
        self.alias_called: str | None = None

    async def handle_backend_call(self, intent, *, sources="", app, env=None):  # noqa: ANN001, ARG002
        self.exact_called = True
        return "EXACT"

    async def handle_backend_alias(self, alias, *, sources="", intent="", app, env=None):  # noqa: ANN001, ARG002
        self.alias_called = alias
        return f"ALIAS:{alias}"


class _NonProfilePlugin(Plugin):
    """Mirrors python-runner: a dispatch target that is NOT profile-capable."""

    name = "python-runner"
    backend_call_paths = ["/python"]
    # supports_profile_aliases intentionally absent (getattr default False).

    async def handle_backend_call(self, intent, *, sources="", app, env=None):  # noqa: ANN001, ARG002
        return "PYTHON"


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


class _RealAliasPlugin(BackendApiPluginBase):
    """A real profile-capable plugin wired to a recording backend — exercises the
    genuine handle_backend_alias -> execute_profile_text -> backend.run path."""

    name = "faketest-backend-api"
    backend_call_paths = ["/faketest"]

    def __init__(self, backend: Backend, profiles: dict[str, BackendProfile]) -> None:
        self.settings = SimpleNamespace(  # type: ignore[assignment]
            default_model=None, timeout_seconds=300.0, profiles=profiles
        )
        self._api_config = BackendApiConfig(
            name="faketest-backend-api",
            path_prefix="/faketest",
            default_model="provider/hardcoded-default",
            backend=backend,
            settings=self.settings,
            app=None,
            build_interpreter=lambda: None,
            span_prefix="faketest",
        )


@pytest.mark.asyncio
async def test_exact_path_takes_precedence_over_alias() -> None:
    spy = _SpyBackendPlugin()
    app = _app({"spy": spy})
    node = Url4BackendCall(path="/spy", intent=Url4Text(value="q"))

    result = await _dispatch_backend_call(node, app, Env.root())

    assert result == "EXACT"
    assert spy.exact_called is True
    assert spy.alias_called is None


@pytest.mark.asyncio
async def test_alias_path_routes_to_handle_backend_alias() -> None:
    spy = _SpyBackendPlugin()
    app = _app({"spy": spy})
    node = Url4BackendCall(path="/spy/oss20b", intent=Url4Text(value="q"))

    result = await _dispatch_backend_call(node, app, Env.root())

    assert result == "ALIAS:oss20b"
    assert spy.alias_called == "oss20b"
    assert spy.exact_called is False


@pytest.mark.asyncio
async def test_multi_segment_suffix_is_rejected() -> None:
    spy = _SpyBackendPlugin()
    app = _app({"spy": spy})
    node = Url4BackendCall(path="/spy/org/model", intent=Url4Text(value="q"))

    with pytest.raises(RuntimeError, match="single segment"):
        await _dispatch_backend_call(node, app, Env.root())
    assert spy.alias_called is None


@pytest.mark.asyncio
async def test_non_profile_plugin_does_not_get_alias_dispatch() -> None:
    """`/python/foo` must stay an unknown backend call, never a profile alias."""
    app = _app({"python-runner": _NonProfilePlugin()})
    node = Url4BackendCall(path="/python/foo", intent=Url4Text(value="q"))

    with pytest.raises(
        RuntimeError, match=r"No active plugin handles the backend call /python/foo"
    ):
        await _dispatch_backend_call(node, app, Env.root())


@pytest.mark.asyncio
async def test_unknown_backend_error_unchanged() -> None:
    app = _app({"spy": _SpyBackendPlugin()})
    node = Url4BackendCall(path="/nope", intent=Url4Text(value="q"))

    with pytest.raises(RuntimeError, match=r"No active plugin handles the backend call /nope"):
        await _dispatch_backend_call(node, app, Env.root())


@pytest.mark.asyncio
async def test_reducer_path_supports_alias() -> None:
    """The ensemble/collection reducer re-enters via _dispatch_backend_call_with_intent,
    so alias support there comes for free from the dispatcher-level fix."""
    spy = _SpyBackendPlugin()
    app = _app({"spy": spy})
    node = Url4BackendCall(path="/spy/oss20b", intent=Url4Text(value="original"))

    result = await _dispatch_backend_call_with_intent(node, '["a","b"]', app, Env.root())

    assert result == "ALIAS:oss20b"
    assert spy.alias_called == "oss20b"


@pytest.mark.asyncio
async def test_alias_sends_profile_model_to_backend_end_to_end() -> None:
    """MANDATORY anti-false-pass: dispatching `/faketest/oss20b` must reach
    backend.run() with the *profile* model, not default_model. Exercises the real
    handle_backend_alias -> execute_profile_text -> backend.run chain."""
    backend = _RecordingBackend()
    plugin = _RealAliasPlugin(
        backend, {"oss20b": BackendProfile(model="huggingface/openai/gpt-oss-20b:cheapest")}
    )
    app = _app({"faketest-backend-api": plugin})
    node = Url4BackendCall(path="/faketest/oss20b", intent=Url4Text(value="answer this"))

    result = await _dispatch_backend_call(node, app, Env.root())

    assert backend.calls[0]["model"] == "huggingface/openai/gpt-oss-20b:cheapest"
    assert backend.calls[0]["prompt"] == "answer this"
    assert "gpt-oss-20b" in result


@pytest.mark.asyncio
async def test_unknown_alias_on_known_backend_reports_clearly() -> None:
    backend = _RecordingBackend()
    plugin = _RealAliasPlugin(backend, {"oss20b": BackendProfile(model="m/x")})
    app = _app({"faketest-backend-api": plugin})
    node = Url4BackendCall(path="/faketest/nope", intent=Url4Text(value="q"))

    with pytest.raises(
        Exception, match="No profile alias 'nope' is configured for backend /faketest"
    ):
        await _dispatch_backend_call(node, app, Env.root())
    assert backend.calls == []


@pytest.mark.asyncio
async def test_reducer_alias_sends_profile_model_to_backend() -> None:
    """Plan line 246: the reducer entry point (_dispatch_backend_call_with_intent,
    used by the collection/ensemble reducers) must also run the alias profile's
    model on backend.run — not merely dispatch to the right plugin."""
    backend = _RecordingBackend()
    plugin = _RealAliasPlugin(
        backend, {"oss20b": BackendProfile(model="huggingface/openai/gpt-oss-20b:cheapest")}
    )
    app = _app({"faketest-backend-api": plugin})
    node = Url4BackendCall(path="/faketest/oss20b", intent=Url4Text(value="original"))

    result = await _dispatch_backend_call_with_intent(node, '["a","b"]', app, Env.root())

    assert backend.calls[0]["model"] == "huggingface/openai/gpt-oss-20b:cheapest"
    assert "gpt-oss-20b" in result
