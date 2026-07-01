"""Unit tests for the shared backend-api route helpers.

Specifically covers the SF-115 boundary check that rejects CLI-only
fields explicitly at the ``/run`` route.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from screamingface.plugins.backend_api_base.models import BackendProfile, RunRequest
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELD_DEFAULTS,
    CLI_ONLY_FIELDS,
)
from screamingface.plugins.llm_base.errors import BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition, extract_text
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    _reject_cli_only_fields,
    build_backend_api_router,
    execute_profile_text,
)


def _default_request(**overrides) -> RunRequest:
    return RunRequest(prompt="hi", **overrides)


def test_default_request_passes() -> None:
    _reject_cli_only_fields(_default_request(), "provider-backend-api")


@pytest.mark.parametrize(
    "field,value",
    [
        ("add_dirs", ["/tmp"]),
        ("mcp_config", "/etc/mcp.json"),
        ("permission_mode", "ask"),
        ("dangerously_skip_permissions", True),
        ("no_session_persistence", False),  # default is True; False is non-default
        ("tools", ["bash"]),
        ("allowed_tools", ["read"]),
        ("disallowed_tools", ["write"]),
    ],
)
def test_each_cli_field_rejected(field: str, value: object) -> None:
    req = _default_request(**{field: value})
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "provider-backend-api")
    assert ei.value.status_code == 422
    assert field in ei.value.detail
    assert "provider-backend-api" in ei.value.detail


def test_multiple_offending_fields_all_named() -> None:
    req = _default_request(mcp_config="/x", tools=["bash"], permission_mode="ask")
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "provider-backend-api")
    detail = ei.value.detail
    for f in ("mcp_config", "tools", "permission_mode"):
        assert f in detail


def test_constant_covers_runrequest_defaults() -> None:
    """Defaults map must match the actual RunRequest defaults — guards
    drift if a new CLI-only field is added without updating both."""
    req = _default_request()
    for f in CLI_ONLY_FIELDS:
        assert getattr(req, f) == CLI_ONLY_FIELD_DEFAULTS[f], (
            f"Default mismatch for {f}: model={getattr(req, f)!r} "
            f"vs constant={CLI_ONLY_FIELD_DEFAULTS[f]!r}"
        )


class _RateLimitedBackend(Backend):
    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        raise BackendError("rate limited", status=429, retry_after=2.1)


class _FallbackBackend(Backend):
    def __init__(self) -> None:
        self.models: list[str] = []

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        self.models.append(model)
        if model == "primary/model":
            raise BackendError("rate limited", status=429, retry_after=2.1)
        return CoreMessage(role="assistant", content="fallback ok")


class _OkBackend(Backend):
    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        return CoreMessage(role="assistant", content="ok")


def test_backend_error_retry_after_becomes_response_header() -> None:
    app = FastAPI()
    settings = SimpleNamespace(default_model=None, timeout_seconds=300.0, profiles={})
    router = build_backend_api_router(
        BackendApiConfig(
            name="test-backend-api",
            path_prefix="/test",
            default_model="test/model",
            backend=_RateLimitedBackend(),
            settings=settings,
            app=app,
            build_interpreter=lambda: None,
            span_prefix="test",
        )
    )
    app.include_router(router)

    resp = TestClient(app).post("/test/run", json={"prompt": "hi"})

    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "3"


def test_run_retries_configured_fallback_model_on_429() -> None:
    app = FastAPI()
    backend = _FallbackBackend()
    settings = SimpleNamespace(
        default_model=None,
        fallback_model="fallback/model",
        timeout_seconds=300.0,
        profiles={},
    )
    router = build_backend_api_router(
        BackendApiConfig(
            name="test-backend-api",
            path_prefix="/test",
            default_model="primary/model",
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=lambda: None,
            span_prefix="test",
        )
    )
    app.include_router(router)

    resp = TestClient(app).post("/test/run", json={"prompt": "hi"})

    assert resp.status_code == 200
    assert resp.json()["so"] == "fallback ok"
    assert backend.models == ["primary/model", "fallback/model"]


# ---------------------------------------------------------------------------
# SF-346: shared profile execution helper (execute_profile_text)
#
# URL4 model/profile aliases dispatch through this helper. The invariant that
# matters most: the profile's own `model` must reach ``backend.run()`` — a naive
# implementation can false-pass by dispatching to the right backend while still
# running ``default_model``. Every test here asserts the *recorded* model/prompt.
# ---------------------------------------------------------------------------


class _RecordingBackend(Backend):
    """Backend that records what it was asked to run."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,
    ) -> CoreMessage:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "timeout_seconds": timeout_seconds,
                "prompt": extract_text(messages[0]) if messages else "",
            }
        )
        return CoreMessage(role="assistant", content=f"ran {model}")


def _profile_cfg(
    backend: Backend,
    profiles: dict[str, BackendProfile],
    *,
    default_model: str = "provider/hardcoded-default",
    settings_default_model: str | None = None,
) -> BackendApiConfig:
    settings = SimpleNamespace(
        default_model=settings_default_model,
        timeout_seconds=300.0,
        profiles=profiles,
    )
    return BackendApiConfig(
        name="test-backend-api",
        path_prefix="/test",
        default_model=default_model,
        backend=backend,
        settings=settings,
        app=None,
        build_interpreter=lambda: None,
        span_prefix="test",
    )


@pytest.mark.asyncio
async def test_execute_profile_text_sends_profile_model_to_backend() -> None:
    """MANDATORY anti-false-pass: the profile's model — not default_model — runs."""
    backend = _RecordingBackend()
    cfg = _profile_cfg(
        backend,
        {"oss20b": BackendProfile(model="huggingface/openai/gpt-oss-20b:cheapest")},
        default_model="provider/hardcoded-default",
        settings_default_model="huggingface/settings-default",
    )

    result = await execute_profile_text(cfg, "oss20b", packed_context="", intent="answer this")

    assert backend.calls[0]["model"] == "huggingface/openai/gpt-oss-20b:cheapest"
    assert backend.calls[0]["model"] != "huggingface/settings-default"
    assert backend.calls[0]["model"] != "provider/hardcoded-default"
    assert "gpt-oss-20b" in result  # _RecordingBackend echoes the model it ran


@pytest.mark.asyncio
async def test_execute_profile_text_intent_first_ordering() -> None:
    """URL4 parity: prompt is ``intent\\n\\nsources`` (matches Url4Interpreter),
    NOT the route's context-first ordering."""
    backend = _RecordingBackend()
    cfg = _profile_cfg(backend, {"oss20b": BackendProfile(model="m/x")})

    await execute_profile_text(cfg, "oss20b", packed_context="CONTEXT", intent="QUESTION")

    assert backend.calls[0]["prompt"] == "QUESTION\n\nCONTEXT"


@pytest.mark.asyncio
async def test_execute_profile_text_paren_context_wins_over_profile_context() -> None:
    backend = _RecordingBackend()
    cfg = _profile_cfg(backend, {"oss20b": BackendProfile(model="m/x", context="PROFILE_CONTEXT")})

    await execute_profile_text(cfg, "oss20b", packed_context="PAREN_CONTEXT", intent="Q")

    assert backend.calls[0]["prompt"] == "Q\n\nPAREN_CONTEXT"
    assert "PROFILE_CONTEXT" not in backend.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_execute_profile_text_profile_context_used_when_parens_empty() -> None:
    backend = _RecordingBackend()
    cfg = _profile_cfg(backend, {"oss20b": BackendProfile(model="m/x", context="PROFILE_CONTEXT")})

    await execute_profile_text(cfg, "oss20b", packed_context="", intent="Q")

    assert backend.calls[0]["prompt"] == "Q\n\nPROFILE_CONTEXT"


@pytest.mark.asyncio
async def test_execute_profile_text_carries_system_prompt_and_timeout() -> None:
    backend = _RecordingBackend()
    cfg = _profile_cfg(
        backend,
        {
            "oss20b": BackendProfile(
                model="m/x",
                system_prompt="SYS",
                append_system_prompt="MORE",
                timeout_seconds=42.0,
            )
        },
    )

    await execute_profile_text(cfg, "oss20b", packed_context="", intent="Q")

    assert backend.calls[0]["system"] == "SYS\n\nMORE"
    assert backend.calls[0]["timeout_seconds"] == 42.0


@pytest.mark.asyncio
async def test_execute_profile_text_none_model_uses_settings_default() -> None:
    """A profile with no model uses settings.default_model (not the hardcoded cfg default)."""
    backend = _RecordingBackend()
    cfg = _profile_cfg(
        backend,
        {"bare": BackendProfile(model=None)},
        default_model="provider/hardcoded-default",
        settings_default_model="settings/chosen",
    )

    await execute_profile_text(cfg, "bare", packed_context="", intent="Q")

    assert backend.calls[0]["model"] == "settings/chosen"


@pytest.mark.asyncio
async def test_execute_profile_text_unknown_profile_raises() -> None:
    backend = _RecordingBackend()
    cfg = _profile_cfg(backend, {"oss20b": BackendProfile(model="m/x")})

    with pytest.raises(Exception, match="nope"):
        await execute_profile_text(cfg, "nope", packed_context="", intent="Q")
    assert backend.calls == []


@pytest.mark.asyncio
async def test_execute_profile_text_retries_profile_fallback_model_on_429() -> None:
    """The profile's own fallback_model is carried into the RunRequest and used
    on a 429 — locks BackendProfile.fallback_model -> RunRequest.fallback_model
    -> _run_backend_with_fallback for the URL4 alias path (a rate-limit contract
    that would otherwise regress silently)."""
    backend = _FallbackBackend()
    cfg = _profile_cfg(
        backend,
        {"p": BackendProfile(model="primary/model", fallback_model="fallback/model")},
    )

    result = await execute_profile_text(cfg, "p", packed_context="", intent="Q")

    assert backend.models == ["primary/model", "fallback/model"]
    assert "fallback ok" in result


@pytest.mark.asyncio
async def test_execute_profile_text_does_not_reresolve_nonempty_paren_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anti-double-resolution: when the URL4 parens already carry (dispatcher-
    resolved) context, execute_profile_text uses it verbatim and must NOT run it
    back through resolve_str — otherwise already-fetched context would be
    re-fetched or re-interpreted as a URL4 expression."""
    calls: list[str] = []

    async def _spy_resolve_str(expr: str, app: object = None, env: object = None) -> str:
        calls.append(expr)
        return f"RERESOLVED:{expr}"

    monkeypatch.setattr("screamingface.plugins.url4_executor.url4.resolve_str", _spy_resolve_str)
    backend = _RecordingBackend()
    cfg = _profile_cfg(backend, {"p": BackendProfile(model="m/x", context="PROFILE_CTX")})

    await execute_profile_text(cfg, "p", packed_context="ALREADY_RESOLVED", intent="Q")

    assert calls == []  # non-empty parens → resolve_str never invoked
    assert backend.calls[0]["prompt"] == "Q\n\nALREADY_RESOLVED"
    assert "RERESOLVED" not in backend.calls[0]["prompt"]
