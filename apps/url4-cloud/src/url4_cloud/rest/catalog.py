"""``GET /v1/models`` — the cached, credential-scoped model catalog (spec §5).

FEATURE: model-catalog discovery.

STORY: as a client about to compose a url4 expression, I ask url4-cloud which models I can address
— and get back exactly what aigateway would have told me directly, without url4-cloud holding a
credential of its own.

Owns request-side concerns only (credential resolution, conditional-request/ETag handling, mapping
``CatalogError`` to RFC 9457 problems); the actual upstream fetch and per-credential caching live
in ``url4_cloud.catalog.cache.CatalogService``.

Every response is tied to the caller's credential, which is why ``Cache-Control`` is unconditionally
``private`` and ``Vary`` names all three credential headers.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from url4_cloud.auth import ProblemException
from url4_cloud.catalog.cache import CatalogService
from url4_cloud.catalog.port import CatalogError, Credential
from url4_cloud.rest._credentials import bearer_token

logger = logging.getLogger(__name__)

router = APIRouter()

# INVARIANT: names every header that can change the response body. Without it a shared cache is
# free to serve one caller's catalog to another — the header-level counterpart of keying the cache
# by credential (spec §5.2, §6.3).
_VARY = "Authorization, X-Profile"

# RFC 9110 §11.6.1: a 401 must carry a challenge. `Bearer` with no realm is deliberate — a realm
# would name this deployment's identity provider to an unauthenticated caller.
_CHALLENGE = {"WWW-Authenticate": "Bearer"}

_MODELS_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"description": "The models this credential can address."},
    304: {"description": "The catalog is unchanged since the supplied `If-None-Match`."},
    401: {"description": "No aigateway credential was supplied, or aigateway refused it."},
    502: {"description": "aigateway returned an unusable catalog."},
    503: {"description": "The catalog is not configured on this deployment."},
    504: {"description": "aigateway did not respond in time."},
}

_CREDENTIAL_DESC = (
    "Bearer aigateway credential. Forwarded upstream verbatim — url4-cloud never verifies it."
)

@router.get(
    "/v1/models",
    tags=["Catalog"],
    summary="List the models this credential can address",
    responses=_MODELS_RESPONSES,
    description=(
        "Proxy aigateway's model listing for the caller's own credential, from a per-credential "
        "cache.\n\n"
        "A credential is required: ``Authorization: Bearer <token>``, matching ``GET /?q=``. "
        "url4-cloud holds no credential of its own and verifies nothing — aigateway does.\n\n"
        "The body is aigateway's, verbatim. Responses are cached per credential, so "
        "``Cache-Control`` is ``private`` and ``ETag``/``If-None-Match`` are scoped to that "
        "caller's catalog."
    ),
)
async def list_models(
    request: Request,
    authorization: Annotated[
        str | None, Header(alias="Authorization", description=_CREDENTIAL_DESC)
    ] = None,
    x_profile: Annotated[
        str | None, Header(alias="X-Profile", description="Optional aigateway routing profile.")
    ] = None,
    if_none_match: Annotated[
        str | None, Header(alias="If-None-Match", description="Conditional-request validator.")
    ] = None,
) -> Response:
    """Proxy aigateway's model listing for the caller's own credential, from a per-credential cache.

    A credential is required: ``Authorization: Bearer <token>``, matching ``GET /?q=``.
    url4-cloud holds no credential of its own and verifies nothing — aigateway does.

    The body is aigateway's, verbatim. Responses are cached per credential, so ``Cache-Control`` is
    ``private`` and ``ETag``/``If-None-Match`` are scoped to that caller's catalog.
    """
    service = _require_service(request)
    credential = _require_credential(authorization, x_profile)
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
    if _validator_matches(if_none_match, catalog.etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=catalog.body, headers=headers)


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


def _require_credential(authorization: str | None, profile: str | None) -> Credential:
    """Resolve the caller's credential, or a 401 — without ever calling upstream.

    INVARIANT: rejecting here rather than forwarding an empty credential is what makes an
    unauthenticated request cost aigateway nothing (spec §11 acceptance 2).

    Raises:
        ProblemException: 401 with a ``WWW-Authenticate: Bearer`` header if the header does
            not supply a usable credential.
    """
    token = bearer_token(authorization)
    if token is None:
        raise ProblemException(
            status=401,
            title="Unauthorized",
            detail="an aigateway credential is required to list models",
            headers=_CHALLENGE,
        )
    return Credential.derive(token, profile)


def _validator_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 §13.1.2 weak comparison of an ``If-None-Match`` list against our ETag.

    WHY weak: the RFC mandates weak comparison for ``If-None-Match``, so a ``W/``-prefixed tag
    added by an intermediary must still register as a match — otherwise a client behind such a
    proxy would re-download the catalog on every poll.
    """
    if if_none_match is None:
        return False
    return any(_tag_matches(raw, etag) for raw in if_none_match.split(","))


def _tag_matches(raw: str, etag: str) -> bool:
    """One entity-tag from an ``If-None-Match`` list, compared weakly."""
    candidate = raw.strip()
    if candidate == "*":
        return True
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    return candidate.strip('"') == etag


__all__ = ["router"]
