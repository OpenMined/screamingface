"""How the orphan reaper is wired into the App: what it asks, when it exists, how it shuts down.

FEATURE: tie a run's lifetime to its audience (OME-890).
"""

import asyncio

import pytest
from _fakes import FixedGate, RecordingJobRunner
from fastapi.testclient import TestClient

from screamingface_engine.app import create_app
from screamingface_engine.config import Settings
from screamingface_engine.reaper import RunReaper
from screamingface_engine.testing import InMemoryEventStream

SECRET = "reaper-wiring-secret"


def _app(
    *,
    grace_s: float = 120.0,
    job_runner: RecordingJobRunner | None = None,
    interest: object | None = None,
):
    settings = Settings(jwt_secret=SECRET, orphan_grace_s=grace_s)
    return create_app(
        settings,
        stream=InMemoryEventStream(),
        job_runner=job_runner,
        interest=interest,  # type: ignore[arg-type]
    )


def test_the_reaper_asks_the_real_registry_and_never_the_subscriber_gate() -> None:
    # INVARIANT — THE TRAP THIS TEST EXISTS FOR: `DenyAllGate`, and every test that injects
    # `FixedGate(False)`, answers "no subscriber" for EVERY topic. Wiring the reaper to that seam
    # instead of the real registry would stop every run in the process one grace window after
    # boot. A refused start is visible and annoying; a silently killed four-hour evaluation is
    # not recoverable. Same call as `rest/routes.py::_deps` taking `registry` over `interest`.
    # If this test ever fails, do NOT relax it.
    app = _app(job_runner=RecordingJobRunner(exists=True), interest=FixedGate(False))
    reaper = app.state.reaper
    assert isinstance(reaper, RunReaper)

    app.state.registry.add("watched")

    assert reaper.is_armed("watched") is False


def test_a_disconnect_arms_the_reaper_through_the_registry() -> None:
    app = _app(job_runner=RecordingJobRunner(exists=True))
    reaper = app.state.reaper

    app.state.registry.add("t")
    assert reaper.is_armed("t") is False

    app.state.registry.remove("t")

    assert reaper.is_armed("t") is True


def test_a_reconnect_disarms_the_reaper_through_the_registry() -> None:
    app = _app(job_runner=RecordingJobRunner(exists=True))
    reaper = app.state.reaper

    app.state.registry.add("t")
    app.state.registry.remove("t")
    app.state.registry.add("t")

    assert reaper.is_armed("t") is False


def test_no_reaper_is_built_without_a_job_runner() -> None:
    # WHY: a stream-only App (`URL4_CLOUD_RUNNER=none`) has nothing to stop, and the many unit
    # tests that inject no runner must not grow a background task.
    app = _app(job_runner=None)

    assert app.state.reaper is None


def test_a_zero_grace_disables_the_reaper() -> None:
    app = _app(grace_s=0.0, job_runner=RecordingJobRunner(exists=True))

    assert app.state.reaper is None


def test_a_negative_grace_is_refused_at_startup() -> None:
    with pytest.raises(ValueError):
        Settings(jwt_secret=SECRET, orphan_grace_s=-1.0)


def test_the_default_grace_leaves_room_above_the_ws_ping_window() -> None:
    # INVARIANT: uvicorn needs up to ws_ping_interval + ws_ping_timeout (~40s on its defaults)
    # to notice a partitioned peer, so the default window must sit comfortably above that or the
    # reaper would race the very detection it depends on.
    assert Settings(jwt_secret=SECRET).orphan_grace_s == 120.0


def test_the_sweep_task_starts_with_the_app_and_is_cancelled_with_it() -> None:
    app = _app(job_runner=RecordingJobRunner(exists=True))

    with TestClient(app):
        task = app.state.reaper_task
        assert isinstance(task, asyncio.Task)
        assert not task.done()

    assert app.state.reaper_task.done()


def test_a_stream_only_app_starts_no_sweep_task() -> None:
    app = _app(job_runner=None)

    with TestClient(app):
        assert app.state.reaper_task is None


def test_the_reaper_metrics_are_registered_and_scrapeable() -> None:
    app = _app(job_runner=RecordingJobRunner(exists=True))

    with TestClient(app) as client:
        body = client.get("/metrics").text

    assert "screamingface_engine_orphan_runs_reaped" in body
    assert "screamingface_engine_orphan_runs_armed" in body


def test_the_armed_gauge_follows_the_registry() -> None:
    # WHY this is worth asserting: the gauge is the only signal that distinguishes "no orphans
    # happened" from "the sweep task died", so it has to track real state, not a constant.
    app = _app(job_runner=RecordingJobRunner(exists=True))
    app.state.registry.add("t")
    app.state.registry.remove("t")

    with TestClient(app) as client:
        body = client.get("/metrics").text

    assert "screamingface_engine_orphan_runs_armed 1.0" in body
