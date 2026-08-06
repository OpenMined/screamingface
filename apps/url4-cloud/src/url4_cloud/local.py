"""Local mode's composition root — the App and the run mode fused into one process.

    url4-cloud serve --local

Runs the whole protocol with no Kubernetes and no NATS: an `InProcessJobRunner` spawns each run
as an `asyncio.Task` in the serving process, and an `InMemoryEventStream` carries its frames to
the same REST sync-hold and WS pump a deployed App reads from JetStream. Everything above the two
swapped adapters — auth, the 428 subscriber gate, sequencing, replay-from, the model catalog — is
the production code path, unmodified.

# INVARIANT: this module is the ONLY place the control plane and the run mode meet, which is why
# `.claude/scripts/check_layering.py` lists it in BOTH `CONTROL_PLANE` and `_EXEMPT` — exactly as
# it does `cli.py`, and for the same reason. Being exempt is not the same as being unexamined:
# naming it in `CONTROL_PLANE` is what puts it in the gate's field of view at all, so a future
# reader sees a declared exception rather than a module that quietly evaded the rule.
#
# INVARIANT: nothing imports this module except `cli.py`. `url4_cloud.app` must stay importable
# without dragging in the engine, which is what keeps a deployed App's cold start unchanged —
# `tests/unit/test_local_app.py` pins the direction of that edge.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI

from url4_cloud import job_env
from url4_cloud.adapters.inprocess import InProcessJobRunner
from url4_cloud.adapters.memory import InMemoryEventStream
from url4_cloud.app import create_app
from url4_cloud.catalog import (
    build_executable_catalog_service,
    build_executable_model_details_source,
)
from url4_cloud.config import INSECURE_DEFAULT_JWT_SECRET, Settings
from url4_cloud.connections import build_connections
from url4_cloud.model_routes import declared_model_ids

_logger = logging.getLogger(__name__)

LOCAL_HOST = "127.0.0.1"
"""INVARIANT: loopback only. Local mode deliberately skips `_require_prod_secret`, so it may be
running on the publicly-known dev JWT secret — anyone who can reach the port could mint a
capability token for any topic. The bind address is what keeps that from being remotely
reachable, and it is not configurable for that reason."""

LOCAL_AIGATEWAY_BASE_URL = "http://127.0.0.1:9105"
"""The local AI Gateway address already declared by the checkout's runner config.

Local mode is the zero-configuration composition root: its runner, model catalog, and provider
connections must all address the same loopback Gateway. A supplied
``URL4_CLOUD_AIGATEWAY_BASE_URL`` still wins, which keeps non-default local stacks configurable.
"""


def _warn_if_insecure(settings: Settings) -> None:
    """Say plainly that auth is open when the dev default secret is in play.

    `create_app_from_env` REFUSES to boot on this secret; local mode accepts it so a developer
    need not mint one, and pairs that with the loopback bind above. The warning exists so the
    trade is visible in the log rather than inferred from the absence of an error.
    """
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        _logger.warning(
            "local mode is using the INSECURE default JWT secret — anyone who can reach %s can "
            "mint a capability token for any topic. Set URL4_CLOUD_JWT_SECRET to change it; "
            "never expose this process beyond loopback.",
            LOCAL_HOST,
        )


def _with_runner_config(env: Mapping[str, str]) -> Mapping[str, str]:
    """Point an unconfigured local run at the repo's own ``url4.toml``.

    The declared world is baked into the IMAGE at ``/etc/url4/url4.toml`` (the Dockerfile copies
    it there) and is not installed by the wheel — so in a dev checkout that path does not exist
    and every local run would terminate as ``failed`` with a missing-config error before it could
    reach a model. Falling back to the checkout's own ``url4.toml``, which sits two levels above
    this package, is what makes `--local` usable straight out of a clone.

    Deliberately narrow: an explicit ``URL4_RUNNER_CONFIG`` always wins, and so does a real
    ``/etc/url4/url4.toml`` — this only fills a gap that exists nowhere but a source checkout.
    """
    if job_env.RUNNER_CONFIG in env or Path(job_env.DEFAULT_RUNNER_CONFIG_PATH).is_file():
        return env
    candidate = Path(__file__).resolve().parents[2] / "url4.toml"
    if not candidate.is_file():
        return env
    _logger.info("local mode: using the checkout's runner config at %s", candidate)
    return {**env, job_env.RUNNER_CONFIG: str(candidate)}


def create_local_app(
    settings: Settings | None = None, *, env: Mapping[str, str] | None = None
) -> FastAPI:
    """Build the local-mode App: in-process runner, in-memory stream, real everything else.

    `env` is the ambient environment each run's executor is built from (the deploy-time half a
    Job would receive via `envFrom`); it defaults to the process environment and is a parameter
    so tests need not mutate `os.environ`.
    """
    settings = settings or Settings()
    if settings.aigateway_base_url is None:
        settings = settings.model_copy(update={"aigateway_base_url": LOCAL_AIGATEWAY_BASE_URL})
    _warn_if_insecure(settings)

    # ONE object, handed to both sides — it is an `EventStream`, so it satisfies the App's
    # `EventConsumer` and the runner's `EventPublisher` at once. That shared instance IS the bus.
    stream = InMemoryEventStream(max_frames_per_topic=settings.local_stream_max_frames)

    # WHY the import is function-local: it is THE line that crosses the layering boundary, and
    # keeping it here means the crossing happens when a local App is actually built rather than on
    # any import of this module. What it defers is `runner.connector`/`runner.executor` and httpx
    # — not the engine itself, which `url4/__init__` has already pulled in via any `url4.streaming`
    # import (see the SCOPE NOTE in `check_layering.py`).
    from url4_cloud.runner.main import build_executor

    run_env = _with_runner_config(env if env is not None else os.environ)
    job_runner = InProcessJobRunner(
        stream,
        build_executor,
        base_env=run_env,
        max_concurrent_runs=settings.local_max_concurrent_runs,
        max_history=settings.local_max_run_history,
    )
    model_ids = declared_model_ids(run_env)
    catalog = build_executable_catalog_service(settings, model_ids)
    model_details = build_executable_model_details_source(settings, model_ids)
    connections = build_connections(settings)
    app = create_app(
        settings,
        stream=stream,
        job_runner=job_runner,
        catalog=catalog,
        model_details=model_details,
        connections=connections,
    )
    app.router.on_shutdown.append(job_runner.aclose)
    if catalog is not None:
        app.router.on_shutdown.append(catalog.aclose)
    if model_details is not None:
        app.router.on_shutdown.append(model_details.aclose)
    if connections is not None:
        app.router.on_shutdown.append(connections.aclose)
    return app


__all__ = ["LOCAL_AIGATEWAY_BASE_URL", "LOCAL_HOST", "create_local_app"]
