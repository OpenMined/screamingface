"""Unit tests for local-mode wiring: dev-secret split + CLI flag/port-check plumbing
(local-mode PRD §7 tests 7-8, docs/plans/url4-cloud-integration/prd/local-mode.md).

Headless: no real server bind except the deliberate occupied-port probe in
``test_main_local_occupied_port_exits_before_uvicorn``, which never reaches ``uvicorn.run`` — the
pre-bind check fires first.
"""

import asyncio
import logging
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

import url4_cloud.app as app_module
from url4_cloud.app import _local_settings, _require_prod_secret, make_local_app
from url4_cloud.cli import main
from url4_cloud.config import Settings
from url4_cloud.jobs.inprocess import InProcessJobRunner
from url4_cloud_nats import InMemoryBus
from url4_cloud_runner.aigateway_connector import (
    AigatewayConfig,
    AigatewayWorld,
    build_aigateway_world,
)
from url4_streaming_protocol import OutboundFrame, TerminatedEvent

_INSECURE_DEFAULT = "dev-insecure-change-me"
_TOKEN = "test-token"  # noqa: S105 - not a real credential
_MODEL_EXPR = "/claude-haiku-4-5(ctx)!'hi'"


def _aigateway_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "hi there"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
    )


async def _build_world(*, token: str = _TOKEN) -> AigatewayWorld:
    cfg = AigatewayConfig(models=("claude-haiku-4-5",))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_aigateway_handler), base_url="http://aigw"
    )
    return await build_aigateway_world(cfg, token=token, client=client)


async def _drain_until_terminated(bus: InMemoryBus, topic: str) -> list[OutboundFrame]:
    frames: list[OutboundFrame] = []
    async for event in bus.subscribe(topic):
        frames.append(event)
        if isinstance(event, TerminatedEvent):
            break
    return frames


async def _schedule_and_drain(
    runner: InProcessJobRunner, bus: InMemoryBus, topic: str, url4: str
) -> list[OutboundFrame]:
    # WHY a single portal-called coroutine: `InProcessJobRunner.schedule` calls
    # `asyncio.get_running_loop()` internally, so it must run IN the app's event loop (the
    # TestClient portal's loop), not the sync test thread — same as `_drain_until_terminated`.
    runner.schedule(topic, url4, deadline_s=60)
    return await asyncio.wait_for(_drain_until_terminated(bus, topic), timeout=2.0)


# --- Deliverable 3: dev-secret split (PRD test 8) --------------------------------------------


def test_local_settings_generates_a_random_secret_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("URL4_CLOUD_JWT_SECRET", raising=False)
    with caplog.at_level(logging.WARNING):
        settings = _local_settings()
    assert settings.jwt_secret != _INSECURE_DEFAULT
    assert len(settings.jwt_secret) == 64
    int(settings.jwt_secret, 16)  # a valid hex string
    assert any("ephemeral dev secret" in record.message for record in caplog.records)


def test_require_prod_secret_rejects_the_insecure_default() -> None:
    with pytest.raises(RuntimeError):
        _require_prod_secret(Settings(jwt_secret=_INSECURE_DEFAULT))


def test_require_prod_secret_accepts_a_real_secret() -> None:
    _require_prod_secret(Settings(jwt_secret="a-real-production-secret"))  # no raise


# --- make_local_app: adapter wiring ------------------------------------------------------------


def test_make_local_app_wires_inmemory_bus_and_inprocess_runner() -> None:
    app = make_local_app()
    assert isinstance(app.state.bus, InMemoryBus)
    assert isinstance(app.state.job_runner, InProcessJobRunner)


# --- Batch 4: local mode's shared aigateway world ------------------------------------------------


@pytest.mark.asyncio
async def test_shared_aigateway_world_routes_a_model_expression_to_it() -> None:
    world = await _build_world()
    app = make_local_app(aigateway=world)
    runner = app.state.job_runner
    bus = app.state.bus
    topic = "shared-world-topic"

    runner.schedule(topic, _MODEL_EXPR, deadline_s=60)

    frames = await asyncio.wait_for(_drain_until_terminated(bus, topic), timeout=2.0)

    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "succeeded"


@pytest.mark.asyncio
async def test_without_a_shared_aigateway_world_stays_deny_by_default() -> None:
    app = make_local_app()
    runner = app.state.job_runner
    bus = app.state.bus
    topic = "deny-by-default-topic"

    runner.schedule(topic, _MODEL_EXPR, deadline_s=60)

    frames = await asyncio.wait_for(_drain_until_terminated(bus, topic), timeout=2.0)

    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "failed"


def test_shutdown_closes_the_shared_aigateway_world_exactly_once() -> None:
    world = asyncio.run(_build_world())
    closed: list[int] = []
    real_aclose = world.aclose

    async def _spy_aclose() -> None:
        closed.append(1)
        await real_aclose()

    world.aclose = _spy_aclose  # type: ignore[method-assign]
    app = make_local_app(aigateway=world)

    # `TestClient.__enter__`/`__exit__` drive the real ASGI lifespan (on_startup/on_shutdown) over
    # a portal in the app's own event loop — the same harness the local-spine tests use.
    with TestClient(app):
        pass

    assert closed == [1]


def test_aigateway_config_builds_the_shared_world_at_startup_from_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIGATEWAY_TOKEN", "env-token")
    monkeypatch.setenv("AIGATEWAY_PROFILE", "env-profile")
    built_world = asyncio.run(_build_world(token="env-token"))
    calls: list[tuple[AigatewayConfig, str, str | None]] = []

    async def _fake_build(
        cfg: AigatewayConfig,
        *,
        token: str,
        profile: str | None = None,
        # Signature sync only: local mode now also forwards the Tavily key (web tools,
        # spec 2026-07-23). Accepted-and-ignored here; pinned by the test below.
        tavily_api_key: str | None = None,
    ) -> AigatewayWorld:
        calls.append((cfg, token, profile))
        return built_world

    monkeypatch.setattr(app_module, "build_aigateway_world", _fake_build)
    cfg = AigatewayConfig(models=("claude-haiku-4-5",))
    app = make_local_app(aigateway_config=cfg)

    with TestClient(app) as client:
        # startup already ran on __enter__ — the fake was called with the env-sourced credentials.
        assert calls == [(cfg, "env-token", "env-profile")]
        portal = client.portal
        assert portal is not None
        frames = portal.call(
            _schedule_and_drain,
            app.state.job_runner,
            app.state.bus,
            "startup-world-topic",
            _MODEL_EXPR,
        )

    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "succeeded"


def test_aigateway_config_without_env_token_stays_deny_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIGATEWAY_TOKEN", raising=False)
    cfg = AigatewayConfig(models=("claude-haiku-4-5",))
    app = make_local_app(aigateway_config=cfg)

    with TestClient(app) as client:
        portal = client.portal
        assert portal is not None
        frames = portal.call(
            _schedule_and_drain,
            app.state.job_runner,
            app.state.bus,
            "no-token-topic",
            _MODEL_EXPR,
        )

    assert isinstance(frames[-1], TerminatedEvent)
    assert frames[-1].data.status == "failed"


# --- Deliverable 5: CLI (PRD test 7) ------------------------------------------------------------


def test_main_local_help_documents_the_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["local", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out
    assert "--port" in out
    assert "--max-runs" in out


def test_main_local_occupied_port_exits_before_uvicorn() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]

        with pytest.raises(SystemExit) as exc_info:
            main(["local", "--port", str(port), "--host", "127.0.0.1"])

    assert exc_info.value.code == 2


# --- Tavily web tools in local mode (spec 2026-07-23, dec:W4) ------------------------------------


def test_local_mode_forwards_the_tavily_key_from_env_into_the_shared_world(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # FEATURE: local mode's single shared world must enable web tools the same way the k8s
    # Runner Job does — from the runner-level TAVILY_API_KEY operator secret.
    monkeypatch.setenv("AIGATEWAY_TOKEN", "env-token")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-dev-local")
    built_world = asyncio.run(_build_world(token="env-token"))
    seen: list[str | None] = []

    async def _fake_build(
        cfg: AigatewayConfig,
        *,
        token: str,
        profile: str | None = None,
        tavily_api_key: str | None = None,
    ) -> AigatewayWorld:
        seen.append(tavily_api_key)
        return built_world

    monkeypatch.setattr(app_module, "build_aigateway_world", _fake_build)
    app = make_local_app(aigateway_config=AigatewayConfig(models=("claude-haiku-4-5",)))

    with TestClient(app):
        assert seen == ["tvly-dev-local"]


def test_local_mode_leaves_tavily_unset_when_the_env_has_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # INVARIANT: deny-by-default (dec:W5) — no key in the env means the world is built without
    # one, so the connector never declares web_search/web_fetch.
    monkeypatch.setenv("AIGATEWAY_TOKEN", "env-token")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    built_world = asyncio.run(_build_world(token="env-token"))
    seen: list[str | None] = []

    async def _fake_build(
        cfg: AigatewayConfig,
        *,
        token: str,
        profile: str | None = None,
        tavily_api_key: str | None = None,
    ) -> AigatewayWorld:
        seen.append(tavily_api_key)
        return built_world

    monkeypatch.setattr(app_module, "build_aigateway_world", _fake_build)
    app = make_local_app(aigateway_config=AigatewayConfig(models=("claude-haiku-4-5",)))

    with TestClient(app):
        assert seen == [None]
