"""The FastAPI composition root for the url4-cloud App.

Builds the App instance: wires the REST, catalog, WS, and ops routers, installs auth/problem
handlers and the metrics middleware, and assembles the injectable adapters (event stream, job
runner, catalog service) that tests substitute for the production ones built here from `Settings`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from url4.streaming.interfaces import EventConsumer, JobRunner
from url4_cloud.adapters.factory import build_job_runner
from url4_cloud.auth import Clock, install_problem_handlers
from url4_cloud.catalog import build_catalog_service
from url4_cloud.catalog.cache import CatalogService
from url4_cloud.config import INSECURE_DEFAULT_JWT_SECRET, Settings
from url4_cloud.metrics import MetricsMiddleware, build_metrics, register_catalog_metrics
from url4_cloud.ops import router as ops_router
from url4_cloud.rest import SubscriberGate, catalog_router
from url4_cloud.rest import router as rest_router
from url4_cloud.schemas import customize_openapi
from url4_cloud.ws import ConnectionRegistry
from url4_cloud.ws import router as ws_router

router = APIRouter()

_DIAGRAMS_DIR = Path(__file__).parent / "assets" / "diagrams"


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
) -> FastAPI:
    """Build the App instance.

    All keyword-only params are DI seams: production wiring supplies real adapters via
    `create_app_from_env`, tests inject fakes/mocks directly.
    """
    settings = settings or Settings()
    app = FastAPI(title="url4-cloud", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.stream = stream
    app.state.job_runner = job_runner
    app.state.catalog = catalog
    app.state.metrics = build_metrics()
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
    app.include_router(router)
    app.include_router(rest_router)
    app.include_router(catalog_router)
    app.include_router(ws_router)
    app.include_router(ops_router)
    app.mount("/diagrams", StaticFiles(directory=_DIAGRAMS_DIR), name="diagrams")
    customize_openapi(app)
    return app


def _require_prod_secret(settings: Settings) -> None:
    """Raise RuntimeError if `settings.jwt_secret` is still the insecure dev default."""
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError("URL4_CLOUD_JWT_SECRET must be set in production")


def create_app_from_env() -> FastAPI:  # pragma: no cover - env/NATS wiring (INFRA rule, spec §11)
    """Production entrypoint (used by `cli.py` via uvicorn's factory mode).

    Builds real adapters from `Settings` — a JetStream event consumer, the configured job-runner
    backend, and the catalog service — then wires them into `create_app` and registers their
    shutdown hooks on the App's router.
    """
    from url4_cloud.adapters.jetstream import JetStreamConsumer

    settings = Settings()
    _require_prod_secret(settings)
    stream = JetStreamConsumer(settings.nats_url)
    job_runner = build_job_runner(settings)
    if job_runner is None:
        logging.warning(
            "URL4_CLOUD_RUNNER is 'none' — this App bridges NATS but cannot schedule runs"
        )
    catalog = build_catalog_service(settings)
    app = create_app(settings, stream=stream, job_runner=job_runner, catalog=catalog)
    app.router.on_shutdown.append(stream.close)
    if catalog is not None:
        app.router.on_shutdown.append(catalog.aclose)
    return app
