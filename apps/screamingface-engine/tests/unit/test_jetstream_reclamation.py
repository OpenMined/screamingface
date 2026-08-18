"""Stream reclamation: the leak that made every production run fail with 10047.

Each run declares its own JetStream stream, and JetStream RESERVES `max_bytes` at creation —
an empty stream still holds the whole reservation. With a 10Gi store and a 256 MiB reservation
the ceiling was 40 streams, and nothing reclaimed them: `max_age` expires MESSAGES, never the
stream object, and the only delete path needs a capability token that dies after 60s. These
tests pin the reclamation that replaces that.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nats.js import JetStreamContext
from nats.js.errors import BadRequestError, NotFoundError, ServerError

from screamingface_engine.adapters.jetstream import (
    DEFAULT_STREAM_MAX_BYTES,
    INSUFFICIENT_RESOURCES_ERR_CODE,
    JetStreamConsumer,
)
from screamingface_engine.subjects import stream_for, subject_for
from url4.streaming.codec import encode
from url4.streaming.protocol import (
    LogData,
    LogEvent,
    TerminatedData,
    TerminatedEvent,
    source_for,
)

pytestmark = pytest.mark.asyncio


def _exhausted() -> ServerError:
    """The exact error production raised."""
    return ServerError(
        code=500,
        err_code=INSUFFICIENT_RESOURCES_ERR_CODE,
        description="insufficient storage resources available",
    )


def _info(
    topic: str,
    *,
    messages: int,
    last_seq: int,
    created_age_s: float = 0.0,
    consumer_count: int = 0,
) -> Any:
    return SimpleNamespace(
        config=SimpleNamespace(name=stream_for(topic)),
        created=datetime.now(UTC) - timedelta(seconds=created_age_s),
        state=SimpleNamespace(messages=messages, last_seq=last_seq, consumer_count=consumer_count),
    )


def _raw(frame: Any) -> Any:
    return SimpleNamespace(data=encode(frame))


def _terminated(topic: str, *, age_s: float) -> Any:
    return _raw(
        TerminatedEvent(
            id="t1",
            source=source_for(topic),
            subject=topic,
            time=datetime.now(UTC) - timedelta(seconds=age_s),
            data=TerminatedData(status="succeeded"),
        )
    )


def _log(topic: str) -> Any:
    return _raw(
        LogEvent(
            id="l1",
            source=source_for(topic, "root"),
            subject=topic,
            time=datetime.now(UTC),
            data=LogData.at("INFO", "still running"),
        )
    )


class _FakeJetStream:
    """A JetStream that can be out of storage, and can be freed by deleting streams."""

    def __init__(
        self,
        *,
        infos: list[Any] | None = None,
        last_msgs: dict[str, Any] | None = None,
        exhausted_until_freed: bool = False,
    ) -> None:
        self.added: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self._infos = infos or []
        self._last_msgs = last_msgs or {}
        self._exhausted_until_freed = exhausted_until_freed

    async def add_stream(self, name: str, subjects: list[str], **kwargs: Any) -> object:
        if self._exhausted_until_freed and not self.deleted:
            raise _exhausted()
        self.added.append({"name": name, "subjects": subjects, **kwargs})
        return object()

    async def streams_info(self, offset: int = 0) -> list[Any]:
        # Honours `offset` like the real API: a paging caller must terminate.
        return list(self._infos)[offset:]

    async def get_last_msg(self, stream_name: str, subject: str, **kwargs: Any) -> Any:
        if stream_name not in self._last_msgs:
            raise NotFoundError
        return self._last_msgs[stream_name]

    async def delete_stream(self, name: str) -> bool:
        self.deleted.append(name)
        self._infos = [i for i in self._infos if i.config.name != name]
        return True


def _consumer(js: _FakeJetStream) -> JetStreamConsumer:
    stream = JetStreamConsumer("nats://unused:4222")
    stream._js = cast(JetStreamContext, js)  # noqa: SLF001
    return stream


async def test_insufficient_resources_is_not_a_bad_request() -> None:
    """REGRESSION: this is why 10047 escaped as an unhandled 500 traceback in production.

    `ensure_stream` caught `BadRequestError` to tolerate an already-declared stream. `ServerError`
    (code 500) and `BadRequestError` (code 400) are SIBLINGS under `APIError`, not parent/child,
    so the exhaustion error sailed straight past that arm.
    """
    assert not issubclass(ServerError, BadRequestError)
    assert isinstance(_exhausted(), BadRequestError) is False


async def test_streams_reserve_fifty_megabytes() -> None:
    """INVARIANT: `max_bytes` is a RESERVATION charged at creation, so it sets the concurrency
    ceiling: store_size / max_bytes. At 256 MiB against a 10Gi store that was 40 runs."""
    assert DEFAULT_STREAM_MAX_BYTES == 50 * 1000 * 1000

    js = _FakeJetStream()
    await _consumer(js).ensure_stream("t")

    assert js.added[0]["max_bytes"] == 50 * 1000 * 1000


async def test_an_existing_stream_is_still_tolerated() -> None:
    class _Exists(_FakeJetStream):
        async def add_stream(self, name: str, subjects: list[str], **kwargs: Any) -> object:
            raise BadRequestError(
                code=400, err_code=10058, description="stream name already in use"
            )

    await _consumer(_Exists()).ensure_stream("t")  # must not raise


async def test_exhaustion_sweeps_orphans_then_retries_once() -> None:
    """The whole point: a run that hits an exhausted store reclaims dead streams and proceeds."""
    js = _FakeJetStream(
        infos=[_info("dead", messages=0, last_seq=42)],
        exhausted_until_freed=True,
    )

    await _consumer(js).ensure_stream("fresh")

    assert js.deleted == [stream_for("dead")]
    assert [a["name"] for a in js.added] == [stream_for("fresh")]


async def test_exhaustion_reraises_when_nothing_can_be_reclaimed() -> None:
    """INVARIANT: the sweep must not become an infinite retry. With no orphan to free, the
    caller has to see the real error rather than a hang."""
    js = _FakeJetStream(infos=[], exhausted_until_freed=True)

    with pytest.raises(ServerError) as exc:
        await _consumer(js).ensure_stream("fresh")

    assert exc.value.err_code == INSUFFICIENT_RESOURCES_ERR_CODE
    assert js.deleted == []


async def test_an_emptied_stream_is_an_orphan_but_a_fresh_one_is_never_swept() -> None:
    """INVARIANT: `last_seq > 0` is load-bearing. A stream that `max_age` emptied and a stream
    created microseconds ago BOTH report `messages == 0`; only the emptied one has ever held a
    message. Without this test the sweep would delete streams out from under starting runs.
    """
    js = _FakeJetStream(
        infos=[
            _info("emptied", messages=0, last_seq=17),
            _info("just-created", messages=0, last_seq=0),
        ],
        exhausted_until_freed=True,
    )

    await _consumer(js).ensure_stream("fresh")

    assert js.deleted == [stream_for("emptied")]


async def test_a_terminated_run_is_reclaimed_only_after_the_drain_grace() -> None:
    """A pod killed during its own grace delay leaves a terminated-but-undeleted stream. Those
    are reclaimable — but not instantly, or the sweep races a client draining the final frames.
    """
    js = _FakeJetStream(
        infos=[
            _info("long-done", messages=5, last_seq=5),
            _info("just-finished", messages=5, last_seq=5),
        ],
        last_msgs={
            stream_for("long-done"): _terminated("long-done", age_s=3600),
            stream_for("just-finished"): _terminated("just-finished", age_s=1),
        },
        exhausted_until_freed=True,
    )

    await _consumer(js).ensure_stream("fresh")

    assert js.deleted == [stream_for("long-done")]


async def test_a_live_run_is_never_reclaimed() -> None:
    """INVARIANT: a stream whose last frame is not terminal belongs to a run still in flight.
    Deleting it destroys the stream AND its consumers, cutting off every attached client."""
    js = _FakeJetStream(
        infos=[_info("in-flight", messages=3, last_seq=3)],
        last_msgs={stream_for("in-flight"): _log("in-flight")},
        exhausted_until_freed=True,
    )

    with pytest.raises(ServerError):
        await _consumer(js).ensure_stream("fresh")

    assert js.deleted == []


async def test_the_sweep_ignores_streams_this_deployment_does_not_own() -> None:
    """INVARIANT: the store may be shared. Only `url4-cloud_*` streams are ours to reclaim."""
    js = _FakeJetStream(
        infos=[
            SimpleNamespace(
                config=SimpleNamespace(name="someone-elses-stream"),
                state=SimpleNamespace(messages=0, last_seq=99),
            )
        ],
        exhausted_until_freed=True,
    )

    with pytest.raises(ServerError):
        await _consumer(js).ensure_stream("fresh")

    assert js.deleted == []


async def test_a_reclaimed_topic_can_be_declared_again() -> None:
    """The memo must not outlive the stream it remembers, or a re-run of a swept topic would
    skip `add_stream` and publish into a stream that no longer exists."""
    js = _FakeJetStream(infos=[_info("dead", messages=0, last_seq=9)])
    stream = _consumer(js)

    await stream.ensure_stream("dead")
    assert stream_for("dead") in [a["name"] for a in js.added]

    await stream._sweep_orphans(cast(JetStreamContext, js))  # noqa: SLF001
    js.added.clear()
    await stream.ensure_stream("dead")

    assert [a["name"] for a in js.added] == [stream_for("dead")]


async def test_subject_naming_is_unchanged_by_reclamation() -> None:
    js = _FakeJetStream()
    await _consumer(js).ensure_stream("t")
    assert js.added[0]["subjects"] == [subject_for("t")]


async def test_a_stream_whose_run_never_published_is_reclaimed_once_it_is_old() -> None:
    """REGRESSION (C1): `messages == 0, last_seq == 0` is not only the FRESH state — it is also
    the PERMANENT state of a topic whose runner never published a frame.

    The control plane creates the stream at attach time, before the Job runs, so an
    ImagePullBackOff, a quota rejection, or a crash during world resolution leaves a stream that
    reserves its full `max_bytes` and can never age out (`max_age` has no messages to expire).
    Without this test the sweep is structurally unable to clear the very outage it exists for.
    """
    js = _FakeJetStream(
        infos=[_info("never-ran", messages=0, last_seq=0, created_age_s=7200)],
        exhausted_until_freed=True,
    )

    await _consumer(js).ensure_stream("fresh")

    assert js.deleted == [stream_for("never-ran")]


async def test_a_stream_created_moments_ago_is_still_never_reclaimed() -> None:
    """INVARIANT: the C1 fix must not reopen the hole `last_seq > 0` was closing — a run that is
    starting right now looks identical except for age."""
    js = _FakeJetStream(
        infos=[_info("starting", messages=0, last_seq=0, created_age_s=2)],
        exhausted_until_freed=True,
    )

    with pytest.raises(ServerError):
        await _consumer(js).ensure_stream("fresh")

    assert js.deleted == []


async def test_an_empty_stream_with_a_client_attached_is_never_reclaimed() -> None:
    """INVARIANT: a live consumer is skew-free proof somebody is waiting on this run. Deleting
    the stream destroys their consumer with it."""
    js = _FakeJetStream(
        infos=[_info("awaited", messages=0, last_seq=0, created_age_s=7200, consumer_count=1)],
        exhausted_until_freed=True,
    )

    with pytest.raises(ServerError):
        await _consumer(js).ensure_stream("fresh")

    assert js.deleted == []


async def test_a_stream_another_process_already_reclaimed_counts_as_freed() -> None:
    """REGRESSION (I2): sweeps race — every runner pod and control-plane replica runs one.

    Two callers hit 10047 and both sweep the same snapshot. The loser's `delete_stream` raises
    NotFoundError because the winner already removed it. Treating that as "nothing reclaimed"
    made the loser re-raise 10047 even though space HAD just been freed, failing a client for
    no reason.
    """

    class _AlreadyGone(_FakeJetStream):
        async def delete_stream(self, name: str) -> bool:
            self.deleted.append(name)
            self._infos = [i for i in self._infos if i.config.name != name]
            raise NotFoundError

    js = _AlreadyGone(
        infos=[_info("raced", messages=0, last_seq=99)],
        exhausted_until_freed=True,
    )

    await _consumer(js).ensure_stream("fresh")

    assert [a["name"] for a in js.added] == [stream_for("fresh")]


async def test_the_sweep_reads_every_page_of_streams() -> None:
    """REGRESSION (I6): `streams_info(offset=0)` is ONE request and the server caps a page at
    256. The reclaimable stream can sit past that boundary, and then the sweep frees nothing
    while the store is full of orphans.
    """
    page_one = [_info(f"pad-{n}", messages=5, last_seq=5) for n in range(256)]
    orphan = _info("beyond-the-page", messages=0, last_seq=3)

    class _Paged(_FakeJetStream):
        async def streams_info(self, offset: int = 0) -> list[Any]:
            return list(self._infos)[offset : offset + 256]

    js = _Paged(infos=[*page_one, orphan], exhausted_until_freed=True)

    await _consumer(js).ensure_stream("fresh")

    assert js.deleted == [stream_for("beyond-the-page")]


async def test_the_retry_is_attempted_exactly_once() -> None:
    """INVARIANT: pins termination structurally. `test_exhaustion_reraises_...` proves the raise
    but would HANG rather than fail if the implementation looped, so count the attempts too."""
    js = _FakeJetStream(infos=[_info("dead", messages=0, last_seq=4)], exhausted_until_freed=True)

    await _consumer(js).ensure_stream("fresh")

    assert len(js.added) == 1
