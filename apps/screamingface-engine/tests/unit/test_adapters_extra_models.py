"""OME-880: both adapters carry the admitted overlay into a run's environment.

FEATURE: run any OpenRouter model (OME-878). An admitted model is only real if
the RUN can route it — the runner builds its world from the run's env, so the
App writes the overlay's ids onto every scheduled run as
`URL4_CLOUD_EXTRA_MODELS` (a provider callable, read at SCHEDULE time so a
model admitted a second ago reaches the very next run).

INVARIANT: the two adapters render ONE contract — a key one writes and the
other omits is a local run that silently diverges from a deployed one.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job

from url4.streaming.interfaces import ExecStep, Executor, TraceContext
from screamingface_engine import job_env
from screamingface_engine.adapters.inprocess import InProcessJobRunner
from screamingface_engine.adapters.k8s import K8sJobRunner
from screamingface_engine.testing import InMemoryEventStream

_TARGET = "openrouter/qwen/qwen2.5-7b-instruct"


class _RecordingBatchApi:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_job(
        self, namespace: str, body: Any, *, _request_timeout: float | None = None
    ) -> FakeCreatedJob:
        self.created.append(dict(body))
        return fake_created_job(f"uid-{body['metadata']['name']}")

    def read_namespaced_job(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(
        self,
        name: str,
        namespace: str,
        *,
        propagation_policy: str = "",
        _request_timeout: float | None = None,
    ) -> object:  # pragma: no cover
        raise NotImplementedError


def _job_env_of(api: _RecordingBatchApi) -> dict[str, str]:
    container = api.created[0]["spec"]["template"]["spec"]["containers"][0]
    return {e["name"]: e["value"] for e in container["env"] if "value" in e}


class _NeverExecutor(Executor):
    """Never executed — these tests assert the env the runner BUILDS."""

    async def execute(  # type: ignore[override]
        self, url4: str, *, trace: TraceContext | None = None
    ) -> AsyncIterator[ExecStep]:  # pragma: no cover - the run is never started
        raise NotImplementedError
        yield  # pragma: no cover - unreachable; makes this an async generator


@pytest.mark.asyncio
async def test_the_k8s_adapter_writes_the_overlay_onto_the_job() -> None:
    api = _RecordingBatchApi()
    runner = K8sJobRunner(api, image="runner:test", extra_models=lambda: (_TARGET,))

    await runner.schedule("t", "gpt(hi)", 60)

    assert json.loads(_job_env_of(api)[job_env.EXTRA_MODELS]) == [_TARGET]


@pytest.mark.asyncio
async def test_an_empty_overlay_writes_nothing() -> None:
    api = _RecordingBatchApi()
    runner = K8sJobRunner(api, image="runner:test", extra_models=lambda: ())

    await runner.schedule("t", "gpt(hi)", 60)

    assert job_env.EXTRA_MODELS not in _job_env_of(api)


def test_the_inprocess_adapter_renders_the_same_key() -> None:
    runner = InProcessJobRunner(
        stream=InMemoryEventStream(),
        executor_factory=lambda env: _NeverExecutor(),
        extra_models=lambda: (_TARGET,),
    )

    env = runner._env("t", "gpt(hi)", 60, None, None, None, None)  # noqa: SLF001

    assert json.loads(env[job_env.EXTRA_MODELS]) == [_TARGET]


def test_the_overlay_is_read_at_schedule_time_not_construction_time() -> None:
    # WHY: a model admitted AFTER the app booted must reach the very next run.
    overlay: list[str] = []
    runner = InProcessJobRunner(
        stream=InMemoryEventStream(),
        executor_factory=lambda env: _NeverExecutor(),
        extra_models=lambda: tuple(overlay),
    )

    before = runner._env("t", "gpt(hi)", 60, None, None, None, None)  # noqa: SLF001
    overlay.append(_TARGET)
    after = runner._env("t", "gpt(hi)", 60, None, None, None, None)  # noqa: SLF001

    assert job_env.EXTRA_MODELS not in before
    assert json.loads(after[job_env.EXTRA_MODELS]) == [_TARGET]


def test_an_ambient_extra_models_value_is_replaced_not_inherited() -> None:
    # INVARIANT: same reset rule as identity/cache policy — `_base_env` is one
    # dict shared by every local run, so a stale overlay value must never leak
    # into a run scheduled after the provider changed.
    stale = {job_env.EXTRA_MODELS: json.dumps(["openrouter/stale/model"])}
    runner = InProcessJobRunner(
        stream=InMemoryEventStream(),
        executor_factory=lambda env: _NeverExecutor(),
        base_env=stale,
        extra_models=lambda: (),
    )

    env = runner._env("t", "gpt(hi)", 60, None, None, None, None)  # noqa: SLF001

    assert job_env.EXTRA_MODELS not in env
