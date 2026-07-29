import logging
from datetime import UTC, datetime

import httpx
import pytest
from _fakes import FixedGate, RecordingJobRunner, ScheduledRun
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.testing import InMemoryEventStream

SECRET = "credential-forwarding-unit-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)
TOKEN = "tok-123"  # noqa: S105 - not a real credential, test fixture only


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _app(job_runner: RecordingJobRunner) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S)
    return create_app(
        settings,
        stream=InMemoryEventStream(),
        job_runner=job_runner,
        clock=lambda: T0,
        interest=FixedGate(),
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_bearer_authorization_and_profile_forward_into_schedule(
    caplog: pytest.LogCaptureFixture,
) -> None:
    topic = "cred-topic-bearer"
    runner = RecordingJobRunner()
    app = _app(runner)

    with caplog.at_level(logging.DEBUG):
        async with _client(app) as client:
            resp = await client.get(
                "/",
                params={"q": "gpt(hi)"},
                headers={
                    "URL4-Capability": _token(topic),
                    "Prefer": "respond-async",
                    "Authorization": f"Bearer {TOKEN}",
                    "X-Profile": "team-a",
                },
            )

    assert resp.status_code == 202
    assert runner.scheduled == [
        ScheduledRun(
            topic=topic,
            url4="gpt(hi)",
            deadline_s=app.state.settings.job_deadline_s,
            traceparent=None,
            credential=TOKEN,
            profile="team-a",
        )
    ]
    assert TOKEN not in resp.text
    for record in caplog.records:
        assert TOKEN not in record.getMessage()


@pytest.mark.asyncio
async def test_absent_authorization_schedules_with_no_credential() -> None:
    topic = "cred-topic-absent"
    runner = RecordingJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={"URL4-Capability": _token(topic), "Prefer": "respond-async"},
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential is None
    assert runner.scheduled[0].profile is None


@pytest.mark.asyncio
async def test_non_bearer_authorization_schedules_with_no_credential() -> None:
    topic = "cred-topic-non-bearer"
    runner = RecordingJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "Authorization": "Basic dXNlcjpwYXNz",
            },
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential is None


@pytest.mark.asyncio
async def test_cf_access_jwt_assertion_forwards_as_the_credential() -> None:
    topic = "cred-topic-cf-access"
    runner = RecordingJobRunner()
    app = _app(runner)
    cf_jwt = "cf-access-session-jwt"  # noqa: S105 - test fixture, not a real credential

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "Cf-Access-Jwt-Assertion": cf_jwt,
            },
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential == cf_jwt


@pytest.mark.asyncio
async def test_cf_access_jwt_assertion_takes_priority_over_client_authorization() -> None:
    topic = "cred-topic-cf-access-priority"
    runner = RecordingJobRunner()
    app = _app(runner)
    cf_jwt = "cf-access-session-jwt"  # noqa: S105

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "Authorization": f"Bearer {TOKEN}",
                "Cf-Access-Jwt-Assertion": cf_jwt,
            },
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential == cf_jwt


@pytest.mark.asyncio
async def test_blank_cf_access_header_falls_back_to_authorization() -> None:
    topic = "cred-topic-cf-access-blank"
    runner = RecordingJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "Authorization": f"Bearer {TOKEN}",
                "Cf-Access-Jwt-Assertion": "",
            },
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential == TOKEN


@pytest.mark.asyncio
async def test_bearer_without_profile_forwards_credential_with_none_profile() -> None:
    topic = "cred-topic-no-profile"
    runner = RecordingJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={
                "URL4-Capability": _token(topic),
                "Prefer": "respond-async",
                "Authorization": f"Bearer {TOKEN}",
            },
        )

    assert resp.status_code == 202
    assert runner.scheduled[0].credential == TOKEN
    assert runner.scheduled[0].profile is None
