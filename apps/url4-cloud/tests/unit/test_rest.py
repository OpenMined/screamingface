"""Behaviour tests for the url4-cloud REST control plane (OME-518; spec §5, docs/protocol.md §7).

Headless: an :class:`InMemoryBus` and a fake ``JobRunner``/``SubscriberGate`` are injected via
``create_app`` — no live NATS, k8s, or models. All HTTP is driven through an ASGI transport so the
whole request (including the sync-hold ``await``) runs in one event loop with the in-memory bus.
"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.auth import JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobAlreadyExists, JobStatus, job_name
from url4_cloud_nats import InMemoryBus
from url4_streaming_protocol import (
    ResultData,
    ResultEvent,
    StartedData,
    StartedEvent,
    TerminatedData,
    TerminatedEvent,
)

SECRET = "rest-unit-secret"
WINDOW_S = 60
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


# --- fakes ----------------------------------------------------------------


class FakeJobRunner:
    """A headless ``JobRunner``: records scheduling/stops; toggles the 409 guards for tests."""

    def __init__(self, *, exists: bool = False, conflict_on_schedule: bool = False) -> None:
        self._exists = exists
        self._conflict = conflict_on_schedule
        self.scheduled: list[tuple[str, str, int, str | None]] = []
        self.stopped: list[str] = []

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
        if self._conflict:
            raise JobAlreadyExists(topic)
        self.scheduled.append((topic, url4, deadline_s, traceparent))
        return job_name(topic)

    def stop(self, topic: str) -> None:
        self.stopped.append(topic)

    def exists(self, topic: str) -> bool:
        return self._exists

    def status(self, topic: str) -> JobStatus:
        return "running"


class FakeGate:
    """A ``SubscriberGate`` whose interest answer is fixed per test."""

    def __init__(self, present: bool) -> None:
        self._present = present

    async def has_subscriber(self, topic: str) -> bool:
        return self._present


# --- helpers --------------------------------------------------------------


def _token(topic: str) -> str:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).sign(topic, T0)


def _cap(topic: str) -> dict[str, str]:
    return {"URL4-Capability": _token(topic)}


def _make_app(
    *,
    bus: InMemoryBus | None = None,
    job_runner: FakeJobRunner | None = None,
    gate_present: bool | None = None,
    sync_max_wait_s: float = 5.0,
) -> FastAPI:
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S, sync_max_wait_s=sync_max_wait_s)
    interest = None if gate_present is None else FakeGate(gate_present)
    return create_app(
        settings,
        bus=bus or InMemoryBus(),
        job_runner=job_runner or FakeJobRunner(),
        clock=lambda: T0,
        interest=interest,
    )


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _terminated(topic: str, status: str) -> TerminatedEvent:
    return TerminatedEvent(
        id=f"term-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=TerminatedData(status=status),  # type: ignore[arg-type]
    )


def _result(topic: str, body: str) -> ResultEvent:
    return ResultEvent(
        id=f"res-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=ResultData(body=body, media_type="application/json"),
    )


def _started(topic: str, url4: str) -> StartedEvent:
    return StartedEvent(
        id=f"start-{topic}",
        source=f"/trace/{topic}/node/root",
        subject=topic,
        data=StartedData(url4=url4),
    )


# --- POST /token ----------------------------------------------------------


@pytest.mark.asyncio
async def test_post_token_returns_a_verifiable_token() -> None:
    app = _make_app()
    async with _client(app) as client:
        resp = await client.post("/token")
    assert resp.status_code == 200
    token = resp.json()["token"]
    claims = JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).verify(token, T0)
    assert isinstance(claims["sub"], str) and len(str(claims["sub"])) == 64


# --- GET: auth + preconditions -------------------------------------------


@pytest.mark.asyncio
async def test_post_token_uses_default_clock_when_none_injected() -> None:
    # No clock injected -> the route's UTC wall-clock fallback signs a token fresh enough to verify.
    settings = Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S)
    app = create_app(settings)
    async with _client(app) as client:
        resp = await client.post("/token")
    assert resp.status_code == 200
    token = resp.json()["token"]
    claims = JwtCodec(secret=SECRET, iat_window_s=WINDOW_S).verify(token, datetime.now(UTC))
    assert isinstance(claims["sub"], str)


@pytest.mark.asyncio
async def test_get_without_capability_is_401_problem_json() -> None:
    app = _make_app(gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_get_without_subscriber_is_428() -> None:
    # gate_present=None -> the app's default DenyAllGate: no subscriber is ever present.
    runner = FakeJobRunner()
    app = _make_app(job_runner=runner)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap("topic-428"))
    assert resp.status_code == 428
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert runner.scheduled == []  # the run is never scheduled with nobody listening


@pytest.mark.asyncio
async def test_get_missing_q_is_400() -> None:
    app = _make_app(gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", headers=_cap("topic-noq"))
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_get_conflict_when_job_exists_is_409() -> None:
    runner = FakeJobRunner(exists=True)
    app = _make_app(job_runner=runner, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap("topic-409a"))
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert runner.scheduled == []


@pytest.mark.asyncio
async def test_get_conflict_when_schedule_raises_is_409() -> None:
    runner = FakeJobRunner(conflict_on_schedule=True)
    app = _make_app(job_runner=runner, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap("topic-409b"))
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")


# --- GET: async (Prefer: respond-async) ----------------------------------


@pytest.mark.asyncio
async def test_get_respond_async_is_202_with_headers() -> None:
    topic = "topic-async"
    runner = FakeJobRunner()
    app = _make_app(job_runner=runner, gate_present=True)
    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt(hi)"},
            headers={**_cap(topic), "Prefer": "respond-async"},
        )
    assert resp.status_code == 202
    assert resp.headers["location"] == f"/?topic={topic}"
    assert resp.headers["preference-applied"] == "respond-async"
    assert runner.scheduled and runner.scheduled[0][0] == topic
    assert runner.scheduled[0][1] == "gpt(hi)"


# --- GET: sync outcome table (§5) ----------------------------------------


@pytest.mark.asyncio
async def test_get_sync_succeeded_is_200_with_result_body() -> None:
    topic = "topic-ok"
    bus = InMemoryBus()
    await bus.publish(topic, _started(topic, "gpt()"))
    await bus.publish(topic, _result(topic, '{"answer": 42}'))
    await bus.publish(topic, _terminated(topic, "succeeded"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap(topic))
    assert resp.status_code == 200
    assert resp.json() == {"answer": 42}


@pytest.mark.asyncio
async def test_get_sync_failed_is_502_problem_json() -> None:
    topic = "topic-fail"
    bus = InMemoryBus()
    await bus.publish(topic, _terminated(topic, "failed"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap(topic))
    assert resp.status_code == 502
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["status"] == 502


@pytest.mark.asyncio
async def test_get_sync_stopped_is_409_problem_json() -> None:
    topic = "topic-stopped"
    bus = InMemoryBus()
    await bus.publish(topic, _terminated(topic, "stopped"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap(topic))
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_get_sync_timed_out_is_504_problem_json() -> None:
    topic = "topic-timeout"
    bus = InMemoryBus()
    await bus.publish(topic, _terminated(topic, "timed_out"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap(topic))
    assert resp.status_code == 504
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_get_sync_degrades_to_202_past_bound() -> None:
    topic = "topic-degrade"
    bus = InMemoryBus()
    # A non-terminal frame exists, but no terminal arrives before the (tiny) sync bound.
    await bus.publish(topic, _started(topic, "slow()"))
    app = _make_app(bus=bus, gate_present=True, sync_max_wait_s=0.1)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "slow()"}, headers=_cap(topic))
    assert resp.status_code == 202
    assert resp.headers["location"] == f"/?topic={topic}"


@pytest.mark.asyncio
async def test_get_prefer_wait_zero_degrades_to_202() -> None:
    topic = "topic-wait0"
    bus = InMemoryBus()
    app = _make_app(bus=bus, gate_present=True, sync_max_wait_s=5.0)
    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "slow()"},
            headers={**_cap(topic), "Prefer": "wait=0"},
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_get_sync_succeeded_without_result_is_empty_200() -> None:
    topic = "topic-ok-noresult"
    bus = InMemoryBus()
    await bus.publish(topic, _terminated(topic, "succeeded"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get("/", params={"q": "gpt()"}, headers=_cap(topic))
    assert resp.status_code == 200
    assert resp.content == b""


@pytest.mark.asyncio
async def test_get_malformed_prefer_wait_falls_back_to_cap() -> None:
    # `wait=abc` is unparseable -> treated as no wait; the run still resolves synchronously.
    topic = "topic-badwait"
    bus = InMemoryBus()
    await bus.publish(topic, _result(topic, '{"answer": 1}'))
    await bus.publish(topic, _terminated(topic, "succeeded"))
    app = _make_app(bus=bus, gate_present=True)
    async with _client(app) as client:
        resp = await client.get(
            "/",
            params={"q": "gpt()"},
            headers={**_cap(topic), "Prefer": "wait=abc"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"answer": 1}


# --- DELETE ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_stops_and_purges_is_204() -> None:
    topic = "topic-del"
    bus = InMemoryBus()
    await bus.publish(topic, _started(topic, "gpt()"))
    runner = FakeJobRunner()
    app = _make_app(bus=bus, job_runner=runner, gate_present=True)
    async with _client(app) as client:
        resp = await client.delete("/", params={"topic": topic}, headers=_cap(topic))
    assert resp.status_code == 204
    assert runner.stopped == [topic]
    # purge dropped the buffered frame: a replay from seq 1 now yields nothing new to consume.
    assert bus._log[topic] == []  # noqa: SLF001 — asserting the purge side effect


@pytest.mark.asyncio
async def test_delete_topic_mismatch_is_403() -> None:
    runner = FakeJobRunner()
    app = _make_app(job_runner=runner, gate_present=True)
    async with _client(app) as client:
        resp = await client.delete("/", params={"topic": "someone-else"}, headers=_cap("mine"))
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert runner.stopped == []
