"""SF Engine provider-connection routes backed by AI Gateway."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, SecretStr

from url4_cloud import job_env
from url4_cloud.auth import ProblemException
from url4_cloud.connections.port import Caller, Connection, ConnectionError, Connections

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Connections"])


class ApiKeyRequest(BaseModel):
    """A provider credential accepted only long enough to forward it to AI Gateway."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    api_key: SecretStr


def _serialize(connection: Connection) -> dict[str, object]:
    return {
        "object": "connection",
        "provider": connection.provider,
        "display_name": connection.display_name,
        "auth_methods": list(connection.auth_methods),
        "status": connection.status,
        "auth_method": connection.auth_method,
        "account_label": connection.account_label,
    }


def _caller(request: Request) -> Caller:
    return Caller(job_env.identity_from_headers(request.headers))


def _service(request: Request) -> Connections:
    service = getattr(request.app.state, "connections", None)
    if service is None:
        raise ProblemException(
            status=503,
            title="Service Unavailable",
            detail="provider connections are not configured on this Engine",
        )
    return service


def _problem(exc: ConnectionError) -> ProblemException:
    logger.info("provider connection request failed: %s", type(exc).__name__)
    return ProblemException(status=exc.status, title=exc.title, detail=exc.detail)


@router.get(
    "/v1/connections",
    summary="List provider connections",
    description="Return the safe connection state exposed to the ScreamingFace Client.",
)
async def list_connections(request: Request) -> dict[str, object]:
    try:
        rows = await _service(request).list(_caller(request))
    except ConnectionError as exc:
        raise _problem(exc) from exc
    return {"object": "list", "data": [_serialize(row) for row in rows]}


@router.put(
    "/v1/connections/{provider}",
    summary="Connect or replace a provider API key",
)
async def connect_provider(
    request: Request,
    body: ApiKeyRequest,
    provider: Annotated[str, Path(min_length=1)],
) -> dict[str, object]:
    try:
        connection = await _service(request).connect(
            _caller(request),
            provider,
            body.api_key.get_secret_value(),
        )
    except ConnectionError as exc:
        raise _problem(exc) from exc
    return _serialize(connection)


@router.delete(
    "/v1/connections/{provider}",
    summary="Disconnect a provider",
)
async def disconnect_provider(
    request: Request,
    provider: Annotated[str, Path(min_length=1)],
) -> dict[str, object]:
    try:
        connection = await _service(request).disconnect(_caller(request), provider)
    except ConnectionError as exc:
        raise _problem(exc) from exc
    return _serialize(connection)


__all__ = ["router"]
