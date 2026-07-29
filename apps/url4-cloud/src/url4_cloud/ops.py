"""Operational and reference endpoints: liveness/readiness probes, the Prometheus scrape, and the
unified Scalar-based API reference pages (OpenAPI + AsyncAPI)."""

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from url4_cloud.metrics import Metrics
from url4_cloud.schemas import build_asyncapi

router = APIRouter()


# WHY: one Scalar reference (a static single-page embed that fetches specs at runtime; one script
# tag, no build dependency) with a document switcher — REST (OpenAPI) + Stream (AsyncAPI 3.x, which
# Scalar renders like OpenAPI since v1.61) via the `sources` array, rather than the `@asyncapi`
# web component (OME-566).
_DOCS_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>url4-cloud API reference</title>
  </head>
  <body>
    <div id="app"></div>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <script>
      Scalar.createApiReference('#app', {
        sources: [
          { url: '/openapi.json', title: 'REST', default: true },
          { url: '/asyncapi.json', title: 'Stream (AsyncAPI)' },
        ],
      })
    </script>
  </body>
</html>
"""


def _scalar_page(title: str, spec_url: str) -> str:
    """Render a single-spec Scalar reference page pointed at `spec_url`."""
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
  </head>
  <body>
    <div id="app"></div>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    <script>
      Scalar.createApiReference('#app', {{ url: '{spec_url}' }})
    </script>
  </body>
</html>
"""


@router.get("/livez", tags=["Ops"], summary="Liveness probe", include_in_schema=False)
def livez() -> dict[str, str]:
    """Liveness probe: reports whether the process is up."""
    return {"status": "live"}


@router.get("/readyz", tags=["Ops"], summary="Readiness probe", include_in_schema=False)
def readyz() -> dict[str, str]:
    """Readiness probe: reports whether the app is wired and ready to serve."""
    return {"status": "ready"}


@router.get("/metrics", tags=["Ops"], summary="OpenMetrics scrape", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Serve the OpenMetrics scrape. Returns 503 if `app.state.metrics` isn't wired."""
    state_metrics = getattr(request.app.state, "metrics", None)
    if not isinstance(state_metrics, Metrics):  # pragma: no cover - always wired by create_app
        return Response(status_code=503)
    return Response(generate_latest(state_metrics.registry), media_type=CONTENT_TYPE_LATEST)


@router.get("/docs", tags=["Ops"], summary="Unified API reference", include_in_schema=False)
def docs() -> HTMLResponse:
    """Serve the unified Scalar reference with a switcher between the REST and Stream specs."""
    return HTMLResponse(_DOCS_HTML)


@router.get("/scalar", tags=["Ops"], summary="OpenAPI reference", include_in_schema=False)
def scalar() -> HTMLResponse:
    """Serve the Scalar reference for the OpenAPI (REST) spec."""
    return HTMLResponse(_scalar_page("url4-cloud API reference", "/openapi.json"))


@router.get("/asyncapi", tags=["Ops"], summary="AsyncAPI reference", include_in_schema=False)
def asyncapi_reference() -> HTMLResponse:
    """Serve the Scalar reference for the AsyncAPI (WS stream) spec."""
    return HTMLResponse(_scalar_page("url4-cloud AsyncAPI reference", "/asyncapi.json"))


@router.get("/asyncapi.json", tags=["Ops"], summary="AsyncAPI 3.0 doc", include_in_schema=False)
def asyncapi() -> JSONResponse:
    """Serve the AsyncAPI 3.0 document describing the `/ws` CloudEvents channel."""
    doc: dict[str, Any] = build_asyncapi()
    return JSONResponse(doc)
