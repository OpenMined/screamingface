"""FastAPI application factory for the url4-cloud control plane."""

from fastapi import APIRouter, FastAPI

from url4_cloud.auth import Clock, install_problem_handlers
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobRunner
from url4_cloud.metrics import MetricsMiddleware, build_metrics
from url4_cloud.ops import router as ops_router
from url4_cloud.rest import SubscriberGate
from url4_cloud.rest import router as rest_router
from url4_cloud.schemas import customize_openapi
from url4_cloud.ws import ConnectionRegistry
from url4_cloud.ws import router as ws_router
from url4_cloud_nats import Bus, NatsBus

router = APIRouter()


# WHY: a bare liveness ping for infra health checks — hidden from the OpenAPI (like the other
# probes in ops.py) so it doesn't clutter the user-facing API reference (OME-566).
@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def create_app(
    settings: Settings | None = None,
    *,
    bus: Bus | None = None,
    job_runner: JobRunner | None = None,
    clock: Clock | None = None,
    interest: SubscriberGate | None = None,
) -> FastAPI:
    """Build the stateless url4-cloud app; deps (bus/job_runner/clock/interest) are injected."""
    settings = settings or Settings()
    # WHY: disable FastAPI's built-in Swagger (/docs) + ReDoc (/redoc) — the Scalar reference at
    # /docs replaces them (OME-565). openapi_url stays /openapi.json (FastAPI serves app.openapi()).
    app = FastAPI(title="url4-cloud", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.bus = bus
    app.state.job_runner = job_runner
    # WHY: per-app OpenMetrics registry + the ASGI counter shim (§9); state must exist before the
    # middleware sees the first request, so it is set here rather than lazily.
    app.state.metrics = build_metrics()
    app.add_middleware(MetricsMiddleware)
    # INVARIANT: the WS bridge (OME-521) tracks live connections here; it is also the real
    # SubscriberGate the REST 428 guard consumes when no gate is injected (§4). Empty ⇒ 428.
    registry = ConnectionRegistry()
    app.state.registry = registry
    app.state.interest = interest if interest is not None else registry
    # WHY: leave app.state.clock unset when not injected so the auth dependency's UTC fallback wins.
    if clock is not None:
        app.state.clock = clock
    install_problem_handlers(app)
    app.include_router(router)
    app.include_router(rest_router)
    app.include_router(ws_router)
    app.include_router(ops_router)
    # Enrich the generated OpenAPI 3.1 with the CloudEvents component schemas + rich info (§12).
    customize_openapi(app)
    return app


def create_app_from_env() -> FastAPI:  # pragma: no cover - env/NATS wiring (INFRA rule, spec §11)
    """Env-wired App for the docker-compose e2e (spec §11): a live NATS ``Bus`` + shutdown close.

    The console/helm ``create_app`` factory injects deps in tests; the compose App service instead
    reads ``URL4_CLOUD_*`` (``Settings``) and binds a real :class:`~url4_cloud_nats.NatsBus`.
    Owner-run only — it touches live NATS, so it is excluded from the headless suite (INFRA rule).
    """
    settings = Settings()
    bus = NatsBus(settings.nats_url)
    app = create_app(settings, bus=bus)
    # Close the NATS connection on ASGI shutdown (Starlette lifespan hook).
    app.router.on_shutdown.append(bus.close)
    return app
