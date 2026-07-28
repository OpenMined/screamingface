"""Concrete ``CatalogSource`` adapter for aigateway's ``/v1/models`` endpoint.

Implements the ``CatalogSource`` port (see ``catalog/port.py``) by forwarding a
caller's credential to aigateway's model-listing endpoint and translating transport
and validation failures into the ``CatalogError`` hierarchy.
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

# WHY: aigateway may refuse a credential with either 401 or 403; both are treated as
# a bad credential (CatalogRejected, always surfaced as 401) rather than CatalogBadResponse.
_REJECTION_STATUSES = frozenset({401, 403})


class AigatewayCatalogSource:
    """Fetches and validates the model catalog from aigateway, per credential."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(self, credential: Credential) -> ModelCatalog:
        """Fetch the catalog for ``credential``, raising a typed ``CatalogError`` on failure.

        401/403 map to ``CatalogRejected``; other >=300 statuses, non-JSON bodies,
        and malformed payloads map to ``CatalogBadResponse``; a timeout maps to
        ``CatalogUnavailable``.
        """
        response = await self._get(credential)
        if response.status_code in _REJECTION_STATUSES:
            logger.info("aigateway refused the catalog request (status=%d)", response.status_code)
            raise CatalogRejected(CatalogRejected.detail)
        if response.status_code >= 300:
            logger.warning("aigateway catalog returned status=%d", response.status_code)
            raise CatalogBadResponse(CatalogBadResponse.detail)
        body = self._decode(response)
        _validate(body)
        return ModelCatalog(body=body, etag=compute_etag(body))

    async def _get(self, credential: Credential) -> httpx.Response:
        """Issue the upstream GET, translating transport failures to ``CatalogError``."""
        try:
            return await self._client.get(_CATALOG_PATH, headers=_headers(credential))
        except httpx.TimeoutException as exc:
            logger.warning("aigateway catalog request timed out")
            raise CatalogUnavailable(CatalogUnavailable.detail) from exc
        except httpx.HTTPError as exc:
            logger.warning("aigateway catalog request failed at the transport layer: %s", exc)
            raise CatalogBadResponse(CatalogBadResponse.detail) from exc

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        """Parse the response body as a JSON object, raising ``CatalogBadResponse`` otherwise."""
        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("aigateway catalog response was not JSON")
            raise CatalogBadResponse(CatalogBadResponse.detail) from exc
        if not isinstance(body, dict):
            raise CatalogBadResponse(CatalogBadResponse.detail)
        return body


def _headers(credential: Credential) -> dict[str, str]:
    """Build the upstream request headers, forwarding the credential's token and profile."""
    headers = {"Authorization": f"Bearer {credential.token.get_secret_value()}"}
    if credential.profile is not None:
        headers["X-Profile"] = credential.profile
    return headers


def _validate(body: dict[str, Any]) -> None:
    """Raise ``CatalogBadResponse`` unless ``body`` is a well-formed OpenAI-style model list."""
    if body.get("object") != "list":
        raise CatalogBadResponse(CatalogBadResponse.detail)
    data = body.get("data")
    if not isinstance(data, list):
        raise CatalogBadResponse(CatalogBadResponse.detail)
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise CatalogBadResponse(CatalogBadResponse.detail)


__all__ = ["AigatewayCatalogSource"]
