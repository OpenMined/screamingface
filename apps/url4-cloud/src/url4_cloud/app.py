"""FastAPI application factory for the url4-cloud control plane."""

from fastapi import APIRouter, FastAPI

from url4_cloud.config import Settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the stateless url4-cloud app. Routers land here as later units add them."""
    settings = settings or Settings()
    app = FastAPI(title="url4-cloud", version="0.1.0")
    app.state.settings = settings
    app.include_router(router)
    return app
