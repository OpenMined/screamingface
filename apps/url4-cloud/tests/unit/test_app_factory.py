from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport

from url4_cloud import cli
from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

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

    assert recorded["app"] == "url4_cloud.app:create_app_from_env"
    assert recorded["factory"] is True
