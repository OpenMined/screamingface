"""``GET /v1/models`` — the cached, credential-scoped model catalog (spec §5).

FEATURE: model-catalog discovery.

STORY: as a client about to compose a url4 expression, I ask url4-cloud which models I can address
and receive the caller-visible AI Gateway models installed in this Engine's declared world.

Owns request-side concerns only (credential resolution, conditional-request/ETag handling, mapping
``CatalogError`` to RFC 9457 problems); the actual upstream fetch and per-credential caching live
in ``url4_cloud.catalog.cache.CatalogService``.

Every response is tied to the caller's credential, which is why ``Cache-Control`` is unconditionally
``private`` and ``Vary`` names all three credential headers.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from url4_cloud import job_env
from url4_cloud.auth import ProblemException
from url4_cloud.catalog.cache import CatalogService
from url4_cloud.catalog.port import (
    CatalogError,
    Credential,
    ModelDetailsError,
    ModelDetailsSource,
)
from url4_cloud.rest.conditional import validator_matches

logger = logging.getLogger(__name__)

router = APIRouter()

# INVARIANT: names every header that can change the response body. Without it a shared cache is
# free to serve one caller's catalog to another — the header-level counterpart of keying the cache
# by caller (spec §5.2, §6.3).
_VARY = "X-Profile, X-User-Email"

# RFC 9110 §11.6.1: a 401 must carry a challenge. `Bearer` with no realm is deliberate — a realm
# would name this deployment's identity provider to an unauthenticated caller. Only used to relay
# an upstream refusal now; this route no longer refuses anyone itself.
_CHALLENGE = {"WWW-Authenticate": "Bearer"}

_MODELS_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"description": "The models this caller can address."},
    304: {"description": "The catalog is unchanged since the supplied `If-None-Match`."},
    401: {"description": "aigateway refused the caller's identity."},
    502: {"description": "aigateway returned an unusable catalog."},
    503: {"description": "The catalog is not configured on this deployment."},
    504: {"description": "aigateway did not respond in time."},
}


@router.get(
    "/v1/models",
    tags=["Catalog"],
    summary="List the models this caller can address",
    responses=_MODELS_RESPONSES,
    description=(
        "List the caller-visible aigateway models installed as routes on this Engine, from a "
        "per-caller cache."
        "\n\n"
        "The caller is the verified ``X-User-Email`` the mesh gateway injects, matching "
        "``GET /?q=``. url4-cloud verifies nothing and holds no credential of its own — aigateway "
        "decides, and refuses the request itself when its mode requires an identity that is "
        "absent. Locally, where aigateway runs with auth disabled, no identity is needed.\n\n"
        "Retained model documents are aigateway's verbatim; models outside this Engine's "
        "declared execution world are omitted. Responses are cached per caller, so "
        "``Cache-Control`` is ``private`` and ``ETag``/``If-None-Match`` are scoped to that "
        "caller's catalog."
    ),
)
async def list_models(
    request: Request,
    x_profile: Annotated[
        str | None, Header(alias="X-Profile", description="Optional aigateway routing profile.")
    ] = None,
    if_none_match: Annotated[
        str | None, Header(alias="If-None-Match", description="Conditional-request validator.")
    ] = None,
) -> Response:
    """List caller-visible AI Gateway models installed in this Engine's execution world.

    The caller is the verified ``X-User-Email`` the mesh gateway injects, matching ``GET /?q=``.
    url4-cloud verifies nothing and holds no credential of its own — aigateway does.

    Retained documents are passed through unchanged. Responses are cached per caller, so
    ``Cache-Control`` is ``private`` and ``ETag``/``If-None-Match`` are scoped to that caller.
    """
    service = _require_service(request)
    credential = _caller(x_profile, request.headers)
    try:
        catalog = await service.fetch(credential)
    except CatalogError as exc:
        # WHY the exception carries its own status/title/detail: the route needs no isinstance
        # ladder, so a new failure mode never means editing this function. The upstream cause is
        # logged; only the generic detail reaches the caller (spec §5.3).
        logger.info("model catalog request failed: %s", type(exc).__name__)
        raise ProblemException(
            status=exc.status,
            title=exc.title,
            detail=exc.detail,
            headers=_CHALLENGE if exc.status == 401 else None,
        ) from exc

    headers = {
        "ETag": f'"{catalog.etag}"',
        "Cache-Control": f"private, max-age={service.max_age_s(credential)}",
        "Vary": _VARY,
    }
    if validator_matches(if_none_match, catalog.etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=catalog.body, headers=headers)


@router.get(
    "/v1/model-parameters",
    tags=["Catalog"],
    summary="Get the profile-bound contract for one model",
)
async def model_parameters(
    request: Request,
    model: Annotated[str, Query(min_length=1)],
    x_profile: Annotated[str | None, Header(alias="X-Profile")] = None,
) -> Response:
    """Proxy AI Gateway's authoritative detailed model contract verbatim."""

    source = _require_model_details(request)
    credential = _caller(x_profile, request.headers)
    try:
        details = await source.fetch_details(model, credential)
    except ModelDetailsError as exc:
        raise ProblemException(status=exc.status, title=exc.title, detail=exc.detail) from exc
    headers = {
        **details.headers,
        "Cache-Control": "private, no-store",
        "Vary": _VARY,
    }
    return JSONResponse(
        content=details.body,
        status_code=details.status_code,
        headers=headers,
    )


def _require_service(request: Request) -> CatalogService:
    """The wired catalog service, or a 503.

    WHY this is checked BEFORE the credential: an unconfigured deployment is an operator problem,
    and answering 401 there would send whoever is debugging it hunting for a credential fault that
    does not exist. The deployment's configuration state is not sensitive.
    """
    service = getattr(request.app.state, "catalog", None)
    if service is None:
        raise ProblemException(
            status=503,
            title="Service Unavailable",
            detail="the model catalog is not configured (URL4_CLOUD_AIGATEWAY_BASE_URL)",
        )
    return service


def _require_model_details(request: Request) -> ModelDetailsSource:
    source = getattr(request.app.state, "model_details", None)
    if source is None:
        raise ProblemException(
            status=503,
            title="Service Unavailable",
            detail="model details are not configured (URL4_CLOUD_AIGATEWAY_BASE_URL)",
        )
    return source


def _caller(profile: str | None, headers: Mapping[str, str]) -> Credential:
    """Resolve who is asking, from the verified identity header the mesh gateway injects.

    WHY there is no 401 here any more: url4-cloud cannot know which auth mode aigateway is in, and
    an absent identity is legitimate in one of them. Deployed, Envoy always injects the header and
    an aigateway in ``cloudflare_headers`` mode 401s a request without it — upstream, where the
    decision belongs. Locally, aigateway runs ``disabled``: every caller is anonymous, no identity
    exists to send, and rejecting here would make the endpoint permanently unusable in dev.

    AIDEV-NOTE: this drops the old "an unauthenticated request costs aigateway nothing" short
    circuit (spec §11 acceptance 2), which was only sound while a bearer token was mandatory. The
    flood protection that remains is `catalog.cache`'s entry cap and single-flight bulkhead.
    """
    return Credential.derive(profile, job_env.identity_from_headers(headers))


__all__ = ["router"]
