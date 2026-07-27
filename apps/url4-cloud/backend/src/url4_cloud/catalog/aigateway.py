"""The aigateway model-catalog adapter — the only place this feature speaks HTTP (spec §6.1).

FEATURE: model-catalog discovery. Fetches ``GET /v1/models`` from aigateway using the CALLER's
credential, so the answer is whatever aigateway would have told that caller directly. url4-cloud
never verifies the credential — aigateway is the sole verifier, exactly as with the per-run
credential ``start_run`` forwards.

AIDEV-NOTE: the validation here intentionally repeats the lessons already encoded in the Runner's
``url4_cloud_runner.aigateway_connector._list_models`` — most importantly that a transparent proxy
can answer ``200`` with an HTML interstitial, so a decode failure must be *named* rather than
escaping as a raw ``JSONDecodeError`` (which would surface as an unhandled 500). The two are
deliberately not shared: the Runner parses to a tuple of model ids for route building, while this
returns the body verbatim for proxying.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogRejected,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    compute_etag,
)

logger = logging.getLogger(__name__)

_CATALOG_PATH = "/v1/models"

# INVARIANT: statuses that mean "your credential was refused" rather than "upstream is broken".
# They map to 401 so the caller can act; everything else non-2xx is a 502 they cannot.
_REJECTION_STATUSES = frozenset({401, 403})


class AigatewayCatalogSource:
    """Fetches and validates aigateway's OpenAI-compatible model listing.

    ``client`` is injected and never closed here — the app that built it owns its lifecycle and
    closes it on ASGI shutdown, matching how the Runner's connector treats an injected client.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(self, credential: Credential) -> ModelCatalog:
        response = await self._get(credential)
        if response.status_code in _REJECTION_STATUSES:
            # WHY log the status but not the body: the body is aigateway's, and echoing it into
            # our logs at info level is how upstream detail ends up somewhere it was not reviewed.
            logger.info("aigateway refused the catalog request (status=%d)", response.status_code)
            raise CatalogRejected(CatalogRejected.detail)
        if response.status_code >= 300:
            logger.warning("aigateway catalog returned status=%d", response.status_code)
            raise CatalogBadResponse(CatalogBadResponse.detail)
        body = self._decode(response)
        _validate(body)
        return ModelCatalog(body=body, etag=compute_etag(body))

    async def _get(self, credential: Credential) -> httpx.Response:
        try:
            return await self._client.get(_CATALOG_PATH, headers=_headers(credential))
        except httpx.TimeoutException as exc:
            # WHY 504 only for timeouts: RFC 9110 reserves it for "did not receive a timely
            # response". A refused or reset connection received no response at all — 502.
            logger.warning("aigateway catalog request timed out")
            raise CatalogUnavailable(CatalogUnavailable.detail) from exc
        except httpx.HTTPError as exc:
            # INVARIANT: `str(exc)` never carries the credential — httpx transport errors quote the
            # URL, not request headers. The `from exc` chain stays for operators; the message the
            # caller sees is the class-level generic detail.
            logger.warning("aigateway catalog request failed at the transport layer: %s", exc)
            raise CatalogBadResponse(CatalogBadResponse.detail) from exc

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("aigateway catalog response was not JSON")
            raise CatalogBadResponse(CatalogBadResponse.detail) from exc
        if not isinstance(body, dict):
            raise CatalogBadResponse(CatalogBadResponse.detail)
        return body


def _headers(credential: Credential) -> dict[str, str]:
    """The upstream headers. ``X-Profile`` is OMITTED, not blanked, when there is no profile."""
    headers = {"Authorization": f"Bearer {credential.token.get_secret_value()}"}
    if credential.profile is not None:
        headers["X-Profile"] = credential.profile
    return headers


def _validate(body: dict[str, Any]) -> None:
    """Reject anything that is not an OpenAI-shaped model listing.

    WHY validate at all when the body is passed through verbatim: a caller receiving
    ``{"detail": "..."}`` with a 200 would treat an error page as an empty catalog. Validating the
    envelope here means a wrong shape becomes an explicit 502 instead of a silently empty list.
    An empty ``data`` array is valid — a gateway with no plugins loaded is a real deployment.
    """
    if body.get("object") != "list":
        raise CatalogBadResponse(CatalogBadResponse.detail)
    data = body.get("data")
    if not isinstance(data, list):
        raise CatalogBadResponse(CatalogBadResponse.detail)
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise CatalogBadResponse(CatalogBadResponse.detail)


__all__ = ["AigatewayCatalogSource"]
