"""Ops + docs surface (spec §12, docs/protocol.md §9).

k8s liveness/readiness probes (`/livez`, `/readyz`), an OpenMetrics scrape (`/metrics`), the
Scalar OpenAPI reference (`/scalar` → `/openapi.json`), the AsyncAPI 3.0 doc (`/asyncapi.json`)
and its rendered reference (`/asyncapi`). Both reference pages are app-served and same-origin, so
`docker compose` serves the viewers with no extra container. All read only ``request.app.state``.
"""

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from url4_cloud.metrics import Metrics
from url4_cloud.schemas import build_asyncapi

router = APIRouter()

# WHY: Scalar is a static single-page reference that fetches the OpenAPI at runtime; we ship the
# minimal documented embed (script tag + data-url) rather than a build dependency. It renders the
# `/openapi.json` this app already serves.
_SCALAR_HTML = """\
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
      Scalar.createApiReference('#app', { url: '/openapi.json' })
    </script>
  </body>
</html>
"""


@router.get("/livez", tags=["Ops"], summary="Liveness probe", include_in_schema=False)
def livez() -> dict[str, str]:
    """k8s liveness probe — the process is up (spec §9)."""
    return {"status": "live"}


@router.get("/readyz", tags=["Ops"], summary="Readiness probe", include_in_schema=False)
def readyz() -> dict[str, str]:
    """k8s readiness probe — the app is wired and can serve (spec §9)."""
    return {"status": "ready"}


@router.get("/metrics", tags=["Ops"], summary="OpenMetrics scrape", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Prometheus/OpenMetrics exposition of the request + gen_ai token counters (spec §9)."""
    state_metrics = getattr(request.app.state, "metrics", None)
    if not isinstance(state_metrics, Metrics):  # pragma: no cover - always wired by create_app
        return Response(status_code=503)
    return Response(generate_latest(state_metrics.registry), media_type=CONTENT_TYPE_LATEST)


@router.get("/scalar", tags=["Ops"], summary="Scalar API reference", include_in_schema=False)
def scalar() -> HTMLResponse:
    """Serve the Scalar reference rendering ``/openapi.json`` (spec §12)."""
    return HTMLResponse(_SCALAR_HTML)


# WHY: the AsyncAPI web-component (a custom element) fetches and renders the raw /asyncapi.json
# same-origin, so the app itself is the WS-schema viewer — no external Studio, no CORS (OME-553).
_ASYNCAPI_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>url4-cloud AsyncAPI reference</title>
    <link
      rel="stylesheet"
      href="https://unpkg.com/@asyncapi/react-component@2/styles/default.min.css"
    />
  </head>
  <body>
    <asyncapi-component schemaUrl="/asyncapi.json"></asyncapi-component>
    <script
      src="https://unpkg.com/@asyncapi/web-component@2/lib/asyncapi-web-component.js"
    ></script>
  </body>
</html>
"""


@router.get("/asyncapi", tags=["Ops"], summary="AsyncAPI reference", include_in_schema=False)
def asyncapi_reference() -> HTMLResponse:
    """Serve the AsyncAPI web-component rendering ``/asyncapi.json`` (spec §12, OME-553)."""
    return HTMLResponse(_ASYNCAPI_HTML)


@router.get("/asyncapi.json", tags=["Ops"], summary="AsyncAPI 3.0 doc", include_in_schema=False)
def asyncapi() -> JSONResponse:
    """The AsyncAPI 3.0 doc for the ``/ws`` CloudEvents channel (spec §12)."""
    doc: dict[str, Any] = build_asyncapi()
    return JSONResponse(doc)
