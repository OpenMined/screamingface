"""FastAPI application factory for the url4-cloud control plane."""

import logging
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from url4_cloud.auth import PROBLEM_MEDIA_TYPE, Clock, Problem, install_problem_handlers
from url4_cloud.config import INSECURE_DEFAULT_JWT_SECRET, Settings
from url4_cloud.jobs.factory import build_job_runner
from url4_cloud.jobs.inprocess import InProcessJobRunner
from url4_cloud.jobs.port import JobRunner
from url4_cloud.metrics import MetricsMiddleware, build_metrics
from url4_cloud.ops import router as ops_router
from url4_cloud.rest import SubscriberGate
from url4_cloud.rest import router as rest_router
from url4_cloud.schemas import customize_openapi
from url4_cloud.ws import ConnectionRegistry
from url4_cloud.ws import router as ws_router
from url4_cloud_nats import Bus, InMemoryBus, NatsBus
from url4_cloud_runner.aigateway_connector import (
    AigatewayConfig,
    AigatewayWorld,
    build_aigateway_world,
)
from url4_cloud_runner.executor import Executor
from url4_cloud_runner.url4_executor import Url4Executor, deny_by_default_world

router = APIRouter()

# Execution-flow diagrams (assets/diagrams/*.svg) served at /diagrams and embedded in the
# OpenAPI description so Scalar renders them inline (OME-555). Shipped via `COPY src ./src`.
_DIAGRAMS_DIR = Path(__file__).parent / "assets" / "diagrams"


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
    # WHY: serve the execution-flow diagrams same-origin so Scalar renders them inline in the
    # OpenAPI description (OME-555).
    app.mount("/diagrams", StaticFiles(directory=_DIAGRAMS_DIR), name="diagrams")
    # Enrich the generated OpenAPI 3.1 with the CloudEvents component schemas + rich info (§12).
    customize_openapi(app)
    return app


def _require_prod_secret(settings: Settings) -> None:
    """Prod hardening (local-mode PRD §3.3.6): refuse to start on the insecure default secret —
    only ``make_local_app``'s dev path is allowed to auto-generate one."""
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError("URL4_CLOUD_JWT_SECRET must be set in production")


def create_app_from_env() -> FastAPI:  # pragma: no cover - env/NATS wiring (INFRA rule, spec §11)
    """Env-wired App for the docker-compose e2e (spec §11): a live NATS ``Bus`` + shutdown close.

    The console/helm ``create_app`` factory injects deps in tests; the compose App service instead
    reads ``URL4_CLOUD_*`` (``Settings``) and binds a real :class:`~url4_cloud_nats.NatsBus`.
    Owner-run only — it touches live NATS, so it is excluded from the headless suite (INFRA rule).
    """
    settings = Settings()
    _require_prod_secret(settings)
    bus = NatsBus(settings.nats_url)
    # INVARIANT: the deployed App must be able to SCHEDULE, not just bridge — the substrate comes
    # from URL4_CLOUD_RUNNER (the chart sets `k8s`). Without this the App mints tokens and streams
    # but every `GET /?q=` is a 503, which is the whole point of the guard in `rest.routes`.
    job_runner = build_job_runner(settings)
    if job_runner is None:
        logging.warning(
            "URL4_CLOUD_RUNNER is 'none' — this App bridges NATS but cannot schedule runs"
        )
    app = create_app(settings, bus=bus, job_runner=job_runner)
    # Close the NATS connection on ASGI shutdown (Starlette lifespan hook).
    app.router.on_shutdown.append(bus.close)
    return app


def _local_settings() -> Settings:
    """Dev-secret split (local-mode PRD §3.3.6): an unset/default ``jwt_secret`` gets a fresh,
    process-lifetime-only random secret — loudly logged, since tokens won't survive a restart."""
    settings = Settings()
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        settings = settings.model_copy(update={"jwt_secret": secrets.token_hex(32)})
        logging.warning("ephemeral dev secret generated — tokens won't survive restart")
    return settings


def _is_run_start(scope: Scope) -> bool:
    # WHY: only a run-START request (`GET /?q=`) is gated — `DELETE /`, `/token`, `/ws`, ops
    # probes, etc. must pass through untouched (Deliverable 4).
    if scope["type"] != "http" or scope["method"] != "GET" or scope["path"] != "/":
        return False
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    return bool(query.get("q"))


def _too_many_runs_response(max_runs: int) -> JSONResponse:
    problem = Problem(
        title="Service Unavailable",
        status=503,
        detail=f"max concurrent local runs ({max_runs}) reached",
    )
    return JSONResponse(
        status_code=503,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _install_max_runs_gate(app: FastAPI, runner: InProcessJobRunner, max_runs: int) -> None:
    """Local-only admission gate (local-mode PRD §3.3.7): 503 a RUN-START request once
    ``runner.active_count()`` is already at ``max_runs`` — short-circuits BEFORE the route
    schedules. An unbounded local task fleet is a laptop-melter, not a feature. Never installed by
    ``create_app`` — prod is unbounded/k8s-scheduled.

    Best-effort, NOT a hard cap: the count is read here but the increment happens later in
    ``schedule``. It is exact only because the pre-schedule path (interest gate, auth) has no
    ``await`` suspension point today — two truly concurrent starts could otherwise both clear the
    gate. Adding any ``await`` before ``schedule`` would loosen the cap by the concurrent slack.
    Also: a gated 503 short-circuits ahead of ``MetricsMiddleware``, so it is not counted in
    ``/metrics`` (acceptable for a dev-mode guard)."""

    class _MaxRunsGate:
        def __init__(self, asgi_app: ASGIApp) -> None:
            self._app = asgi_app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if _is_run_start(scope) and runner.active_count() >= max_runs:
                await _too_many_runs_response(max_runs)(scope, receive, send)
                return
            await self._app(scope, receive, send)

    app.add_middleware(_MaxRunsGate)


@dataclass
class _SharedAigatewayWorld:
    """Mutable holder for local mode's single shared aigateway world (aigateway connector plan
    §Design decision, Batch 4): built once (either injected directly, or lazily at ASGI startup
    from env) and read by every per-run executor factory call — never rebuilt per run."""

    world: AigatewayWorld | None = None


def make_local_app(
    *,
    settings: Settings | None = None,
    max_runs: int = 4,
    executor_factory: Callable[[], Executor] | None = None,
    aigateway: AigatewayWorld | None = None,
    aigateway_config: AigatewayConfig | None = None,
) -> FastAPI:
    """The complete url4-cloud service, entirely in-process: ``InMemoryBus`` +
    ``InProcessJobRunner`` driving the real ``Url4Executor``. Same REST/WS/token protocol as prod
    (``create_app``); only the adapters are swapped (local-mode PRD).

    **Local-mode credential model** (aigateway connector plan §Design decision, Batch 4): unlike
    prod (k8s), which builds a fresh per-run aigateway world from the caller's forwarded
    credential, local mode shares a SINGLE process-level aigateway credential across ONE world
    built once and closed at shutdown — never a per-run world, since a per-run world would force a
    per-run ``GET /v1/models`` fetch and churn ``InProcessJobRunner``'s single-shared-executor-
    factory contract. The per-run ``credential``/``profile`` that ``InProcessJobRunner.schedule``
    accepts (forwarded from the request's ``Authorization`` header, same as prod) is therefore a
    documented no-op here — only the k8s adapter honors it, per request.

    ``aigateway``, when given, is a PRE-BUILT world (tests) used as the shared world from the
    start. Else, ``aigateway_config``, when given, causes the shared world to be built lazily by
    an async ASGI startup hook, IN THE APP'S OWN EVENT LOOP — httpx clients are loop-bound, so it
    must not be built via a separate ``asyncio.run`` before the app's loop starts. The startup
    hook reads ``AIGATEWAY_TOKEN`` (+ optional ``AIGATEWAY_PROFILE``/``TAVILY_API_KEY``) from the
    environment; absent a token, the world stays deny-by-default. Either way, an ASGI shutdown
    hook closes the shared world exactly once, alongside the existing ``runner.aclose``.

    ``executor_factory``, when given, overrides all of the above (existing tests rely on this).
    """
    settings = settings or _local_settings()
    bus = InMemoryBus()
    shared = _SharedAigatewayWorld(world=aigateway)

    def _default_factory() -> Executor:
        if shared.world is not None:
            # NOTE: no `world_aclose=` — the world is shared across every run, so a per-run
            # executor must NOT close it; the shared world is closed once, at ASGI shutdown.
            return Url4Executor(shared.world.node)
        return Url4Executor(deny_by_default_world())

    factory = executor_factory or _default_factory
    runner = InProcessJobRunner(bus, factory)
    app = create_app(settings, bus=bus, job_runner=runner)

    if aigateway is None and aigateway_config is not None:

        async def _build_shared_world() -> None:
            token = os.environ.get("AIGATEWAY_TOKEN")
            if not token:
                return
            profile = os.environ.get("AIGATEWAY_PROFILE")
            # WHY read here rather than from Settings: local mode's world is built from the
            # process env alongside the aigateway credential, and `TAVILY_API_KEY` is the same
            # runner-level operator secret the Runner Job reads (spec 2026-07-23, dec:W4).
            # Absent => web tools stay off (deny-by-default, dec:W5).
            shared.world = await build_aigateway_world(
                aigateway_config,
                token=token,
                profile=profile,
                tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            )

        app.router.on_startup.append(_build_shared_world)

    async def _close_shared_world() -> None:
        if shared.world is not None:
            await shared.world.aclose()

    # Cancel every in-flight run and await it on ASGI shutdown (local-mode PRD §3.3.4); the shared
    # aigateway world (if any was ever built) is closed alongside it, exactly once.
    app.router.on_shutdown.append(runner.aclose)
    app.router.on_shutdown.append(_close_shared_world)
    _install_max_runs_gate(app, runner, max_runs)
    return app
