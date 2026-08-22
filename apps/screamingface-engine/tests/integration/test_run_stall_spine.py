"""End to end: a run whose Job can never start delivers one generic WARN to the attached client.

FEATURE: surface a generic capacity warning when a Runner Job cannot be scheduled (OME-948).

STORY: as a researcher whose evaluation was accepted but whose Runner Pod can never be created
(the namespace is at its quota), I am told the runner service is at capacity instead of staring
at a silently non-progressing run for up to 16 hours.

WHY this file exists beside the unit tests: `test_run_stall.py` proves the policy against
fakes and `test_app_factory.py` proves the wiring gate. Neither proves the SPINE — that a REAL
WebSocket attached to the real registry and bridge receives the WARN frame the watcher pushed
through `notify`, and that the `/metrics` surface reports the stall. That is what this covers,
assembled the same way `test_orphan_reaper_spine.py` assembles its local-mode App — except the
runner is a fake that reports every run as `scheduled` forever, because a k8s scheduler refusal
is exactly the state a real local runner cannot produce.

AIDEV-NOTE: these tests wait on CONDITIONS with a deadline, never on a fixed sleep. The watch's
sweep runs on the App's own event loop inside `TestClient`'s portal, so the test thread cannot
await it directly; the observable it polls instead is `/metrics`, the same surface an operator
uses. `run_stall_warn_after_s` is set small so a sweep tick actually lands during the test —
`_TICKS_PER_GRACE` floors the tick at 1s, so budget just over a second per warn.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping

import pytest
from fastapi.testclient import TestClient

from screamingface_engine.app import create_app
from screamingface_engine.config import Settings
from screamingface_engine.ports import IdentityAwareJobRunner
from screamingface_engine.run_stall import STALL_MESSAGE
from screamingface_engine.testing import InMemoryEventStream
from url4.streaming.interfaces import JobStatus

SECRET = "s" * 32

# Small enough that a 1s sweep tick closes the stall window during the test, large enough that a
# pod-creation latency of a few seconds would never be mistaken for a stall in production terms.
SHORT_BOUND_S = 0.2

_WAIT_TIMEOUT_S = 10.0
_POLL_S = 0.02


class _StuckRunner(IdentityAwareJobRunner):
    """Every run is accepted and then never gets a Pod — `scheduled` forever."""

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
        return "scheduled"


@pytest.fixture
def stuck() -> Iterator[TestClient]:
    settings = Settings(
        jwt_secret=SECRET,
        runner="k8s",
        run_stall_warn_after_s=SHORT_BOUND_S,
        # `runner="k8s"` refuses a filesystem artifact store (OME-929), so the site-backed
        # tests must declare the object store; nothing here ever touches the network.
        artifact_store="s3",
        artifact_s3_endpoint_url="http://minio:9000",
        artifact_s3_bucket="tests",
        artifact_s3_region="us-east-1",
        artifact_s3_access_key="test",
        artifact_s3_secret_key="test",
        # The run never completes, so a sync hold would block for the full default 30s. Every
        # test starts with `Prefer: respond-async`; this is the safety net.
        sync_max_wait_s=0.2,
    )
    app = create_app(
        settings,
        stream=InMemoryEventStream(),
        job_runner=_StuckRunner(),
    )
    with TestClient(app) as client:
        yield client


def _cap(token: str) -> dict[str, str]:
    return {"URL4-Capability": token}


def _async_start(token: str) -> dict[str, str]:
    return {"URL4-Capability": token, "Prefer": "respond-async"}


def _token(client: TestClient) -> str:
    response = client.post("/token")
    assert response.status_code == 200
    return str(response.json()["token"])


def _attach(ws: object) -> None:
    ws.send_text(  # type: ignore[attr-defined]
        json.dumps(
            {
                "specversion": "1.0",
                "id": "attach-1",
                "source": "/test",
                "type": "ai.url4.attach",
                "data": {},
            }
        )
    )


def _metric(client: TestClient, name: str) -> float:
    """One metric's current value, read from the real `/metrics` surface."""
    for line in client.get("/metrics").text.splitlines():
        if line.startswith(f"{name} "):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def _warned(client: TestClient) -> float:
    # prometheus_client appends `_total` to counter families on the wire.
    return _metric(client, "screamingface_engine_run_stalls_warned_total")


def _wait_until(predicate: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + _WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise AssertionError(f"timed out after {_WAIT_TIMEOUT_S}s waiting for {what}")


def test_a_stuck_run_delivers_one_generic_warn_to_the_attached_client(stuck: TestClient) -> None:
    token = _token(stuck)
    with stuck.websocket_connect(f"/ws?ticket={token}") as ws:
        _attach(ws)
        response = stuck.get("/?q='hi'!'go'", headers=_async_start(token))
        assert response.status_code == 202

        # The notice fires one sweep tick after the stall bound closes, on the App's loop.
        _wait_until(lambda: _warned(stuck) >= 1.0, "the stall warn to fire")
        # The notice was already queued to THIS socket at warn time; drain until the WARN frame.
        for _ in range(8):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "ai.url4.log" and frame["data"]["severity_text"] == "WARN":
                assert frame["data"]["body"] == STALL_MESSAGE
                return
        raise AssertionError("the attached client never received the WARN log frame")
