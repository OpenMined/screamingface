"""FastAPI application factory for the url4-cloud control plane."""

from fastapi import APIRouter, FastAPI

from url4_cloud.auth import Clock, install_problem_handlers
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobRunner
from url4_cloud.rest import DenyAllGate, SubscriberGate
from url4_cloud.rest import router as rest_router
from url4_cloud_nats import Bus

router = APIRouter()


@router.get("/healthz")
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
    app = FastAPI(title="url4-cloud", version="0.1.0")
    app.state.settings = settings
    app.state.bus = bus
    app.state.job_runner = job_runner
    # INVARIANT: interest defaults to DenyAllGate — start is 428 until a real gate wires (§4).
    app.state.interest = interest if interest is not None else DenyAllGate()
    # WHY: leave app.state.clock unset when not injected so the auth dependency's UTC fallback wins.
    if clock is not None:
        app.state.clock = clock
    install_problem_handlers(app)
    app.include_router(router)
    app.include_router(rest_router)
    return app
