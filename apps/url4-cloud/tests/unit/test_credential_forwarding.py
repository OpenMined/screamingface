"""Identity forwarding — the aigateway credential hop, App → JobRunner (plan §5.3, dec:A).

Mirrors the ``traceparent`` inbound-propagation hop test shape (``test_traceparent.py`` §5): a
headless ``create_app`` + a fake ``JobRunner`` that only records the ``credential``/``profile``
kwargs ``schedule`` was called with. ``Authorization`` is free for this hop — the run capability
rides the dedicated ``URL4-Capability`` header (OME-556) — so a Bearer token there is forwarded
verbatim; anything else (absent, non-Bearer) forwards nothing.
"""

import logging
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobStatus, job_name
from url4_cloud_nats import InMemoryBus

SECRET = "credential-forwarding-unit-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)
TOKEN = "tok-123"  # noqa: S105 - not a real credential, test fixture only


class _FakeJobRunner:
    """A headless ``JobRunner`` that only records the ``credential``/``profile`` kwargs it was
    scheduled with (mirrors ``test_traceparent.py``'s ``_FakeJobRunner``)."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str, int, str | None, str | None]] = []

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str:
        self.scheduled.append((topic, url4, deadline_s, credential, profile))
        return job_name(topic)

    def stop(self, topic: str) -> None:
        raise NotImplementedError

    def exists(self, topic: str) -> bool:
        return False

    def status(self, topic: str) -> JobStatus:
        return "running"


class _FakeGate:
    async def has_subscriber(self, topic: str) -> bool:
        return True


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _app(job_runner: _FakeJobRunner) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S)
    return create_app(
        settings, bus=InMemoryBus(), job_runner=job_runner, clock=lambda: T0, interest=_FakeGate()
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_bearer_authorization_and_profile_forward_into_schedule(
    caplog: pytest.LogCaptureFixture,
) -> None:
    topic = "cred-topic-bearer"
    runner = _FakeJobRunner()
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
        (topic, "gpt(hi)", app.state.settings.job_deadline_s, TOKEN, "team-a")
    ]
    # SECURITY: the credential must never appear in logs or in the response.
    assert TOKEN not in resp.text
    for record in caplog.records:
        assert TOKEN not in record.getMessage()


@pytest.mark.asyncio
async def test_absent_authorization_schedules_with_no_credential() -> None:
    topic = "cred-topic-absent"
    runner = _FakeJobRunner()
    app = _app(runner)

    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={"URL4-Capability": _token(topic), "Prefer": "respond-async"},
        )

    assert resp.status_code == 202
    assert runner.scheduled[0][3] is None
    assert runner.scheduled[0][4] is None


@pytest.mark.asyncio
async def test_non_bearer_authorization_schedules_with_no_credential() -> None:
    topic = "cred-topic-non-bearer"
    runner = _FakeJobRunner()
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
    assert runner.scheduled[0][3] is None


@pytest.mark.asyncio
async def test_cf_access_jwt_assertion_forwards_as_the_credential() -> None:
    # Cloudflare Access silently attaches this header to every proxied request once a browser
    # has completed its edge login — no client code involved. url4-cloud never verifies it (it
    # is opaque here, forwarded exactly like an SDK-supplied Authorization bearer); aigateway,
    # the actual consumer, verifies the signature.
    topic = "cred-topic-cf-access"
    runner = _FakeJobRunner()
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
    assert runner.scheduled[0][3] == cf_jwt


@pytest.mark.asyncio
async def test_cf_access_jwt_assertion_takes_priority_over_client_authorization() -> None:
    # WHY CF Access wins: it is the edge-verified "you are logged in" signal (network topology +
    # aigateway's own signature check are what make it trustworthy, not url4-cloud). A
    # client-editable Authorization header stays available as the fallback for direct/service
    # callers that never go through Cloudflare Access at all.
    topic = "cred-topic-cf-access-priority"
    runner = _FakeJobRunner()
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
    assert runner.scheduled[0][3] == cf_jwt


@pytest.mark.asyncio
async def test_blank_cf_access_header_falls_back_to_authorization() -> None:
    topic = "cred-topic-cf-access-blank"
    runner = _FakeJobRunner()
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
    assert runner.scheduled[0][3] == TOKEN


@pytest.mark.asyncio
async def test_bearer_without_profile_forwards_credential_with_none_profile() -> None:
    topic = "cred-topic-no-profile"
    runner = _FakeJobRunner()
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
    assert runner.scheduled[0][3] == TOKEN
    assert runner.scheduled[0][4] is None
