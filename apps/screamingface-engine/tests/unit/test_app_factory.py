from collections.abc import Mapping
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport

from screamingface_engine import cli
from screamingface_engine.app import create_app
from screamingface_engine.auth import JwtCodec
from screamingface_engine.config import Settings
from screamingface_engine.ports import IdentityAwareJobRunner
from screamingface_engine.run_stall import RunStallWatcher
from screamingface_engine.testing import InMemoryEventStream
from url4.streaming.interfaces import JobStatus

pytestmark = pytest.mark.asyncio

SECRET = "app-factory-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


class _PresentGate:
    async def has_subscriber(self, topic: str) -> bool:
        return True


def _unconfigured_app() -> object:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S)
    return create_app(
        settings,
        stream=InMemoryEventStream(),
        job_runner=None,
        clock=lambda: T0,
        interest=_PresentGate(),
    )


def _cap(topic: str) -> dict[str, str]:
    return {"URL4-Capability": JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)}


@pytest.mark.anyio
async def test_run_start_without_job_runner_is_503_not_500() -> None:
    app = _unconfigured_app()
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/", params={"q": "'hi'!'go'"}, headers=_cap("topic-a"))

    assert resp.status_code == 503
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 503


@pytest.mark.anyio
async def test_stop_without_job_runner_is_503_not_500() -> None:
    app = _unconfigured_app()
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/", params={"topic": "topic-a"}, headers=_cap("topic-a"))

    assert resp.status_code == 503


def test_prod_cli_serves_the_env_wired_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def _fake_run(app: object, **kwargs: object) -> None:
        recorded["app"] = app
        recorded.update(kwargs)

    monkeypatch.setattr("uvicorn.run", _fake_run)
    cli.main([])

    assert recorded["app"] == "screamingface_engine.app:create_app_from_env"
    assert recorded["factory"] is True


class _FakeRunner(IdentityAwareJobRunner):
    """A structural fake the wiring gate needs: a non-None runner that is not k8s-backed."""

    async def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
        identity: Mapping[str, str] | None = None,
        cache: object | None = None,
    ) -> str:
        return topic

    async def stop(self, topic: str) -> None: ...

    async def exists(self, topic: str) -> bool:
        return False

    async def status(self, topic: str) -> JobStatus:
        return "not_found"


def _k8s_settings() -> Settings:
    """Settings that pass the App's boot-time fences: `runner="k8s"` refuses a filesystem
    artifact store (OME-929 — a Job pod's disk dies with it), so the k8s wiring tests must
    declare the object store. No network is touched at construction.
    """
    return Settings(
        jwt_secret=SECRET,
        iat_window_s=WINDOW_S,
        runner="k8s",
        artifact_store="s3",
        artifact_s3_endpoint_url="http://minio:9000",
        artifact_s3_bucket="tests",
        artifact_s3_region="us-east-1",
        artifact_s3_access_key="test",
        artifact_s3_secret_key="test",
    )


@pytest.mark.asyncio
async def test_run_stall_watch_is_absent_outside_k8s() -> None:
    app = create_app(
        Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S),
        stream=InMemoryEventStream(),
        job_runner=_FakeRunner(),
    )
    # Local mode cannot stall silently (an in-process run fails fast or 503s at accept), so the
    # watch must not be wired — a useless background task on every local boot would be the smell.
    assert app.state.stall_watcher is None


@pytest.mark.asyncio
async def test_run_stall_watch_is_present_for_a_k8s_runner() -> None:
    app = create_app(
        _k8s_settings(),
        stream=InMemoryEventStream(),
        job_runner=_FakeRunner(),
    )
    watcher = app.state.stall_watcher
    assert isinstance(watcher, RunStallWatcher)
    assert watcher.tick_s >= 1.0
