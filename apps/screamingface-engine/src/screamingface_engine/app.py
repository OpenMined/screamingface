"""The FastAPI composition root for the screamingface-engine App.

Builds the App instance: wires the REST, model discovery, WS, and ops routers, installs
auth/problem handlers and the metrics middleware, and assembles the injectable adapters that
tests substitute for the production ones built here from `Settings`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from screamingface_engine.adapters.factory import build_job_runner
from screamingface_engine.artifacts import ArtifactStore
from screamingface_engine.auth import Clock, install_problem_handlers
from screamingface_engine.benchmarks import EMPTY_BENCHMARKS, BenchmarkRegistry
from screamingface_engine.benchmarks.builtins import BUILTIN_BENCHMARKS
from screamingface_engine.catalog import build_executable_catalog_service
from screamingface_engine.catalog.cache import CatalogService
from screamingface_engine.catalog.port import ModelParameterSource
from screamingface_engine.config import INSECURE_DEFAULT_JWT_SECRET, Settings
from screamingface_engine.connections import build_connections
from screamingface_engine.connections.port import Connections
from screamingface_engine.metrics import MetricsMiddleware, build_metrics, register_catalog_metrics
from screamingface_engine.ops import router as ops_router
from screamingface_engine.rest import (
    SubscriberGate,
    artifact_router,
    benchmark_router,
    catalog_router,
    connection_router,
)
from screamingface_engine.rest import router as rest_router
from screamingface_engine.schemas import customize_openapi
from screamingface_engine.ws import ConnectionRegistry
from screamingface_engine.ws import router as ws_router
from url4.streaming.interfaces import EventConsumer, JobRunner

router = APIRouter()

_DIAGRAMS_DIR = Path(__file__).parent / "assets" / "diagrams"

# Mounted in this order by `create_app`. A tuple rather than seven calls: the wiring is data, and
# every new surface (benchmarks, connections, …) would otherwise grow the builder itself.
_ROUTERS = (
    router,
    rest_router,
    artifact_router,
    benchmark_router,
    catalog_router,
    connection_router,
    ws_router,
    ops_router,
)


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def create_app(
    settings: Settings | None = None,
    *,
    stream: EventConsumer | None = None,
    job_runner: JobRunner | None = None,
    clock: Clock | None = None,
    interest: SubscriberGate | None = None,
    catalog: CatalogService | None = None,
    model_parameters: ModelParameterSource | None = None,
    connections: Connections | None = None,
    benchmarks: BenchmarkRegistry = EMPTY_BENCHMARKS,
) -> FastAPI:
    """Build the App instance.

    All keyword-only params are DI seams: production wiring supplies real adapters via
    `create_app_from_env`, tests inject fakes/mocks directly.
    """
    settings = settings or Settings()
    app = FastAPI(title="screamingface-engine", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.stream = stream
    app.state.job_runner = job_runner
    app.state.catalog = catalog
    app.state.model_parameters = model_parameters
    app.state.connections = connections
    app.state.benchmarks = benchmarks
    app.state.metrics = build_metrics()
    # FEATURE: deliver large results in full (OME-892) — the serve side of the spill store.
    artifact_store = ArtifactStore(Path(settings.artifacts_dir))
    app.state.artifact_store = artifact_store
    # WHY startup + periodic: artifacts are deleted on fetch, so the only leak source is
    # parcels nobody redeemed (crashed runs, vanished clients). The boot sweep clears the
    # backlog immediately; the periodic task covers a hosted App that stays up for weeks
    # between redeploys — startup-only would let abandoned parcels pool until the next
    # restart (owner decision on OME-892).
    _install_artifact_sweeper(app, artifact_store, settings)
    # WHY: pass a getter, not `catalog` directly — the collector re-reads app.state.catalog on
    # every /metrics scrape rather than capturing the value built here.
    register_catalog_metrics(app.state.metrics, lambda: app.state.catalog)
    app.add_middleware(MetricsMiddleware)
    registry = ConnectionRegistry()
    app.state.registry = registry
    app.state.interest = interest if interest is not None else registry
    if clock is not None:
        app.state.clock = clock
    install_problem_handlers(app)
    for api_router in _ROUTERS:
        app.include_router(api_router)
    app.mount("/diagrams", StaticFiles(directory=_DIAGRAMS_DIR), name="diagrams")
    customize_openapi(app)
    return app


# RFC 7518 §3.2: an HMAC key must be at least as long as the hash output — 32 bytes for SHA-256.
# PyJWT warns below this; here it is refused, because the token is the whole authorization model.
_logger = logging.getLogger(__name__)


def _install_artifact_sweeper(app: FastAPI, store: ArtifactStore, settings: Settings) -> None:
    """Wire the artifact TTL sweep: once at startup, then every sweep interval for life.

    FEATURE: deliver large results in full (OME-892). The loop is an asyncio task on the
    App's own event loop — cancelled at shutdown so no task outlives the App. The sweep
    itself runs in a worker thread (`asyncio.to_thread`): it is directory I/O, and the
    event loop that pumps every WebSocket must never block on a disk scan.
    """

    async def _sweep_once() -> None:
        await asyncio.to_thread(store.sweep, ttl_seconds=settings.artifact_ttl_s)

    async def _sweep_forever() -> None:
        while True:
            await asyncio.sleep(settings.artifact_sweep_interval_s)
            # INVARIANT: one failed sweep must not kill the sweeper — an unhandled
            # exception here would end the task silently and disk cleanup would stop
            # until the next redeploy, exactly the leak the periodic sweep exists to
            # prevent. Log and keep the cadence.
            try:
                await _sweep_once()
            except Exception:
                _logger.exception("artifact sweep failed; retrying next interval")

    async def _start() -> None:
        await _sweep_once()
        app.state.artifact_sweep_task = asyncio.get_running_loop().create_task(_sweep_forever())

    async def _stop() -> None:
        task = getattr(app.state, "artifact_sweep_task", None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app.router.on_startup.append(_start)
    app.router.on_shutdown.append(_stop)


_MIN_JWT_SECRET_BYTES = 32


def _require_prod_secret(settings: Settings) -> None:
    """Raise RuntimeError if `settings.jwt_secret` is unset or too weak to sign a capability.

    Sentinel equality alone was not enough: it rejected the shipped dev default but accepted any
    other string, so a 4-character production secret passed. The capability token IS the topic
    authorization, so a brute-forceable signing key is a full authorization bypass — refused at
    boot rather than at the first forged token.
    """
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError("URL4_CLOUD_JWT_SECRET must be set in production")
    if len(settings.jwt_secret.encode("utf-8")) < _MIN_JWT_SECRET_BYTES:
        raise RuntimeError(
            f"URL4_CLOUD_JWT_SECRET must be at least {_MIN_JWT_SECRET_BYTES} bytes "
            f"(RFC 7518 §3.2 for HS256); it signs the topic-capability token"
        )


def create_app_from_env() -> FastAPI:  # pragma: no cover - env/NATS wiring (INFRA rule, spec §11)
    """Production entrypoint (used by `cli.py` via uvicorn's factory mode).

    Builds real adapters from `Settings` — a JetStream event consumer, the configured job-runner
    backend, and the catalog service — then wires them into `create_app` and registers their
    shutdown hooks on the App's router.
    """
    from screamingface_engine.adapters.jetstream import JetStreamConsumer

    settings = Settings()
    _require_prod_secret(settings)
    stream = JetStreamConsumer(settings.nats_url)
    job_runner = build_job_runner(settings)
    if job_runner is None:
        logging.warning(
            "URL4_CLOUD_RUNNER is 'none' — this App bridges NATS but cannot schedule runs"
        )
    catalog = build_executable_catalog_service(settings, os.environ)
    connections = build_connections(settings)
    app = create_app(
        settings,
        stream=stream,
        job_runner=job_runner,
        catalog=catalog,
        model_parameters=catalog.model_parameter_source if catalog is not None else None,
        connections=connections,
        benchmarks=BUILTIN_BENCHMARKS,
    )
    app.router.on_shutdown.append(stream.close)
    if catalog is not None:
        app.router.on_shutdown.append(catalog.aclose)
    if connections is not None:
        app.router.on_shutdown.append(connections.aclose)
    return app
