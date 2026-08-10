"""The runner reclaims its own stream when the run ends.

WHY the runner and not the control plane: `DELETE /` needs a capability token, and those expire
`iat_window_s` (60s) after minting with no way to re-issue one for an existing topic — so any run
longer than a minute could never tear its own stream down. That is the leak that filled the store.
"""

from typing import Any, cast

import pytest
from nats.errors import NoServersError
from nats.js.errors import ServerError

from url4_cloud import job_env
from url4_cloud.adapters.jetstream import JetStreamPublisher
from url4_cloud.runner.main import run_and_reclaim, stream_grace_s

DEFAULT_STREAM_GRACE_S = job_env.DEFAULT_STREAM_GRACE_S

pytestmark = pytest.mark.asyncio

TOPIC = "run-topic"


class _Recorder:
    """Records teardown ordering: the grace delay must precede the delete."""

    def __init__(self, *, delete_fails: bool = False) -> None:
        self.events: list[str] = []
        self._delete_fails = delete_fails
        self.delete_error: Exception | None = None

    async def sleep(self, seconds: float) -> None:
        self.events.append(f"slept:{seconds}")

    async def delete_stream(self, topic: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        if self._delete_fails:
            raise ServerError(code=500, err_code=10047, description="still out of storage")
        self.events.append(f"deleted:{topic}")


def _publisher(rec: _Recorder) -> JetStreamPublisher:
    return cast(JetStreamPublisher, cast(Any, rec))


async def test_the_stream_is_reclaimed_after_a_successful_run() -> None:
    rec = _Recorder()

    async def _run() -> None:
        rec.events.append("ran")

    await run_and_reclaim(_publisher(rec), TOPIC, _run, grace_s=30.0, sleep=rec.sleep)

    assert rec.events == ["ran", "slept:30.0", f"deleted:{TOPIC}"]


async def test_the_stream_is_reclaimed_even_when_the_run_fails() -> None:
    """INVARIANT: reclamation is in a `finally`. A run that raises is exactly the run whose
    stream would otherwise linger, and every leaked stream holds its full reservation."""
    rec = _Recorder()

    async def _boom() -> None:
        raise RuntimeError("execution blew up")

    with pytest.raises(RuntimeError, match="execution blew up"):
        await run_and_reclaim(_publisher(rec), TOPIC, _boom, grace_s=1.0, sleep=rec.sleep)

    assert rec.events == ["slept:1.0", f"deleted:{TOPIC}"]


async def test_the_grace_delay_precedes_the_delete() -> None:
    """INVARIANT: `delete_stream` destroys the stream AND its consumers. Deleting the instant the
    terminal frame is published races a client that has not drained yet — it would never receive
    the terminal frame and would hang until its own timeout.
    """
    rec = _Recorder()

    async def _run() -> None:
        rec.events.append("ran")

    await run_and_reclaim(_publisher(rec), TOPIC, _run, grace_s=60.0, sleep=rec.sleep)

    assert rec.events.index("slept:60.0") < rec.events.index(f"deleted:{TOPIC}")


async def test_a_failed_teardown_does_not_mask_the_run_outcome() -> None:
    """A run that succeeded must not be reported as failed because reclamation could not finish;
    the sweep will pick the stream up later."""
    rec = _Recorder(delete_fails=True)

    async def _run() -> None:
        rec.events.append("ran")

    await run_and_reclaim(_publisher(rec), TOPIC, _run, grace_s=0.0, sleep=rec.sleep)

    assert "ran" in rec.events


async def test_a_failed_teardown_does_not_swallow_the_run_failure() -> None:
    rec = _Recorder(delete_fails=True)

    async def _boom() -> None:
        raise RuntimeError("the real failure")

    with pytest.raises(RuntimeError, match="the real failure"):
        await run_and_reclaim(_publisher(rec), TOPIC, _boom, grace_s=0.0, sleep=rec.sleep)


async def test_a_broker_outage_during_teardown_does_not_fail_a_good_run() -> None:
    """REGRESSION (I3): `delete_stream` connects lazily, so it can raise `NoServersError` /
    `ConnectionClosedError` / `nats.errors.TimeoutError` — NONE of which are `APIError`.

    A broker blip during a long run would otherwise turn a run that published
    `Terminated(succeeded)` into a Job reported Failed.
    """
    rec = _Recorder()
    rec.delete_error = NoServersError()

    async def _run() -> None:
        rec.events.append("ran")

    await run_and_reclaim(_publisher(rec), TOPIC, _run, grace_s=0.0, sleep=rec.sleep)

    assert "ran" in rec.events


async def test_a_broker_outage_during_teardown_does_not_replace_the_run_failure() -> None:
    """INVARIANT: a raise inside `finally` SUPERSEDES the exception already propagating, so a
    teardown error would erase the real cause of a failed run from the Job's logs."""
    rec = _Recorder()
    rec.delete_error = NoServersError()

    async def _boom() -> None:
        raise RuntimeError("the real failure")

    with pytest.raises(RuntimeError, match="the real failure"):
        await run_and_reclaim(_publisher(rec), TOPIC, _boom, grace_s=0.0, sleep=rec.sleep)


async def test_the_grace_window_is_configurable_and_defaults_to_the_attach_window() -> None:
    """60s matches `iat_window_s` — the widest window in which any client can still be attached."""
    assert DEFAULT_STREAM_GRACE_S == 60.0
    assert stream_grace_s({}) == 60.0
    assert stream_grace_s({job_env.STREAM_GRACE_S: "5"}) == 5.0


async def test_an_unparseable_grace_falls_back_to_the_default() -> None:
    """INVARIANT: a typo in the env must not crash every Job at teardown."""
    assert stream_grace_s({job_env.STREAM_GRACE_S: "not-a-number"}) == DEFAULT_STREAM_GRACE_S
