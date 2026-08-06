"""AI Gateway adapter for model-list and profile-bound model-detail discovery.

Implements both discovery ports in ``catalog/port.py`` with one HTTP client and one identity
boundary. The model list is cached by its decorator; detailed parameter contracts deliberately
pass through uncached.
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
    ModelParameterBadResponse,
    ModelParameterResponse,
    compute_etag,
)

logger = logging.getLogger(__name__)

_CATALOG_PATH = "/v1/models"
_MODEL_PARAMETERS_PATH = "/v1/model-parameters"
_CALLER_CORRECTABLE_STATUSES = frozenset({400, 401, 403, 404, 409})

# WHY: aigateway may refuse a credential with either 401 or 403; both are treated as
# a bad credential (CatalogRejected, always surfaced as 401) rather than CatalogBadResponse.
_REJECTION_STATUSES = frozenset({401, 403})


class AigatewayCatalogSource:
    """Fetch and minimally validate AI Gateway model discovery for one caller."""

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

    async def fetch_model_parameters(
        self,
        credential: Credential,
        model: str,
    ) -> ModelParameterResponse:
        """Fetch one detailed model contract for the caller's profile."""

        try:
            response = await self._client.get(
                _MODEL_PARAMETERS_PATH,
                params={"model": model},
                headers=_headers(credential),
            )
        except httpx.TimeoutException as exc:
            logger.warning("aigateway model-parameter request timed out")
            raise CatalogUnavailable(CatalogUnavailable.detail) from exc
        except httpx.HTTPError as exc:
            logger.warning("aigateway model-parameter request failed at the transport layer")
            raise ModelParameterBadResponse(ModelParameterBadResponse.detail) from exc
        body = self._decode(
            response,
            bad_response=ModelParameterBadResponse,
            label="model-parameter",
        )
        if response.status_code in _CALLER_CORRECTABLE_STATUSES:
            return ModelParameterResponse(status=response.status_code, body=body)
        if response.status_code >= 300:
            raise ModelParameterBadResponse(ModelParameterBadResponse.detail)
        _validate_model_parameters(body, model)
        return ModelParameterResponse(status=response.status_code, body=body)

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

    def _decode(
        self,
        response: httpx.Response,
        *,
        bad_response: type[CatalogBadResponse] = CatalogBadResponse,
        label: str = "catalog",
    ) -> dict[str, Any]:
        """Parse one upstream response as a JSON object, or raise its typed failure."""
        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("aigateway %s response was not JSON", label)
            raise bad_response(bad_response.detail) from exc
        if not isinstance(body, dict):
            raise bad_response(bad_response.detail)
        return body


def _headers(credential: Credential) -> dict[str, str]:
    """Build the upstream request headers from the credential's identity and profile.

    INVARIANT: the gateway-owned header is written LAST, mirroring ``runner.connector._headers`` —
    the identity mapping is not guaranteed to hold only identity keys, so no value in it can
    displace ``X-Profile``.

    No ``Authorization``: a deployed aigateway (``cloudflare_headers``) reads only the identity
    header, and a local one (``disabled``) reads nothing at all.
    """
    headers = dict(credential.identity)
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


def _validate_model_parameters(body: dict[str, Any], model: str) -> None:
    """Reject a success document that cannot describe the requested model."""

    selected = body.get("model")
    if (
        isinstance(body.get("schema_version"), bool)
        or not isinstance(body.get("schema_version"), int)
        or not isinstance(selected, dict)
        or selected.get("id") != model
        or not isinstance(body.get("parameters"), dict)
        or not isinstance(body.get("tools"), dict)
        or not isinstance(body.get("transport"), dict)
    ):
        raise ModelParameterBadResponse(ModelParameterBadResponse.detail)


__all__ = ["AigatewayCatalogSource"]
