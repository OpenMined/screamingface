from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from tortoise.exceptions import IntegrityError

from aigateway.core.auth.middleware import CurrentAccount
from aigateway.core.credential_strategy_cache import credential_strategy_cache
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth.schemas import (
    CreateOAuthConnectionRequest,
    OAuthConnectionListResponse,
    OAuthConnectionResponse,
    OAuthConnectionTokenResponse,
    PatchOAuthConnectionRequest,
    StartOAuthConnectionResponse,
)
from aigateway.core.oauth.store import (
    OAuthConnectionStore,
    credential_key_for,
    response_from_connection,
)
from aigateway.core.oauth.token_service import (
    OAuthConnectionTokenError,
    oauth_connection_token_service,
)
from aigateway.core.oauth_pkce import generate_pkce, generate_state
from aigateway.core.pending_auth import PendingAuthEntry
from aigateway.core.plugin_base import credential_service_provider_for

from .auth import _redirect_uri_for

router = APIRouter()


@router.get("/v1/oauth/connections", response_model=OAuthConnectionListResponse)
async def list_connections(
    request: Request,
    current: CurrentAccount,
    provider: str | None = None,
    status: str | None = None,
) -> OAuthConnectionListResponse:
    store = _store(request)
    connections = await store.list(str(current.id), provider=provider, status=status)
    return OAuthConnectionListResponse(
        connections=[response_from_connection(connection) for connection in connections]
    )


@router.get("/v1/oauth/connections/{connection_id}", response_model=OAuthConnectionResponse)
async def get_connection(
    connection_id: UUID,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionResponse:
    connection = await _get_visible_connection(request, str(current.id), connection_id)
    return connection


@router.post("/v1/oauth/connections", status_code=201, response_model=StartOAuthConnectionResponse)
async def start_connection_oauth(
    body: CreateOAuthConnectionRequest,
    request: Request,
    current: CurrentAccount,
) -> StartOAuthConnectionResponse:
    plugin = request.app.state.providers.get(body.provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": body.provider}
        )
    cfg = plugin.oauth_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})
    if plugin.requires_oauth_connection_label() and not body.label:
        raise HTTPException(
            status_code=422, detail={"code": "label_required", "provider": body.provider}
        )

    account_id = str(current.id)
    connection_id = uuid4()
    label = body.label or f"pending-{connection_id}"
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()
    redirect_uri: str | None = None
    if body.redirect_uri is not None:
        redirect_uri = await _redirect_uri_for(
            request, body.provider, cfg, state, body.redirect_uri
        )
    store = _store(request)
    if body.label and await store.find_by_label(account_id, body.provider, body.label) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_conflict", "provider": body.provider, "label": body.label},
        )
    try:
        await store.create_pending(
            account_id=account_id,
            provider=body.provider,
            label=label,
            connection_id=connection_id,
            credential_provider=credential_service_provider_for(plugin, body.provider),
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_conflict", "provider": body.provider, "label": label},
        ) from exc

    if redirect_uri is None:
        redirect_uri = await _redirect_uri_for(request, body.provider, cfg, state)
    request.app.state.pending_auth.put(
        state,
        PendingAuthEntry(
            account_id=account_id,
            provider=body.provider,
            profile_name=label,
            profile_id=str(connection_id),
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            connection_id=str(connection_id),
            requested_label=body.label,
        ),
    )

    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(cfg.scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if cfg.extra_authorize_params:
        params.update(cfg.extra_authorize_params)
    return StartOAuthConnectionResponse(
        connection_id=connection_id,
        authorize_url=f"{cfg.authorize_url}?{urlencode(params)}",
        state=state,
    )


@router.patch("/v1/oauth/connections/{connection_id}", response_model=OAuthConnectionResponse)
async def patch_connection(
    connection_id: UUID,
    body: PatchOAuthConnectionRequest,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionResponse:
    store = _store(request)
    connection = await store.get(str(current.id), connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    if connection.status != "active":
        raise HTTPException(status_code=409, detail={"code": "connection_not_active"})
    if body.label is not None:
        connection.label = body.label
    try:
        await connection.save()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_conflict", "provider": connection.provider, "label": body.label},
        ) from exc
    return response_from_connection(connection)


@router.delete("/v1/oauth/connections/{connection_id}", status_code=204)
async def delete_connection(connection_id: UUID, request: Request, current: CurrentAccount) -> None:
    store = _store(request)
    connection = await store.get(str(current.id), connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    await _delete_credentials(request, connection.credential_locator)
    await store.mark_revoked(connection)
    # Evict the shared cached strategy so a deleted connection's still-valid token
    # can't keep being served from memory (SF-282).
    credential_strategy_cache(request.app).evict(credential_key_for(str(current.id), connection_id))


@router.get(
    "/v1/oauth/connections/{connection_id}/token",
    response_model=OAuthConnectionTokenResponse,
)
async def get_connection_token(
    connection_id: UUID,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionTokenResponse:
    """Return a fresh access token for the connection.

    Consumed by SF backend plugins that delegate token management to
    aigateway. The strategy refreshes against the upstream provider if
    the cached credential is within the refresh window.
    """
    from datetime import UTC, datetime

    try:
        token = await oauth_connection_token_service(request.app).get_token(
            account_id=current.id,
            connection_id=connection_id,
            store=_store(request),
            providers=request.app.state.providers,
            credential_store=request.app.state.credential_store,
            http_client_factory_for=lambda provider: getattr(
                request.app.state, f"{provider}_http_factory", None
            ),
        )
    except OAuthConnectionTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return OAuthConnectionTokenResponse(
        access_token=token.access_token,
        expires_at=datetime.fromtimestamp(token.expires_at_ms / 1000, tz=UTC),
    )


@router.post(
    "/v1/oauth/connections/{connection_id}/refresh", response_model=OAuthConnectionResponse
)
async def refresh_connection(
    connection_id: UUID,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionResponse:
    store = _store(request)
    connection = await store.get(str(current.id), connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    if connection.status != "active":
        raise HTTPException(status_code=409, detail={"code": "connection_not_active"})
    plugin = request.app.state.providers.get(connection.provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    strategy = plugin.oauth_strategy_for(
        credential_key_for(current.id, connection.id),
        credential_store=request.app.state.credential_store,
        http_client_factory=getattr(request.app.state, f"{connection.provider}_http_factory", None),
    )
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})
    try:
        await strategy.refresh_credentials()
    except (CredentialNotFoundError, AuthError) as exc:
        await store.mark_error(connection, str(exc))
        credential_strategy_cache(request.app).evict(
            credential_key_for(str(current.id), connection.id)
        )
        raise HTTPException(
            status_code=401, detail={"code": "auth_required", "message": str(exc)}
        ) from exc
    # Manual refresh wrote new tokens to the store; drop the cached instance so the
    # chat path rebuilds and reads them (SF-282).
    credential_strategy_cache(request.app).evict(credential_key_for(str(current.id), connection.id))
    connection = await store.complete(
        connection,
        label=connection.label,
        identity=response_from_connection(connection).account,
    )
    return response_from_connection(connection)


def _store(request: Request) -> OAuthConnectionStore:
    store = getattr(request.app.state, "oauth_connections", None)
    if isinstance(store, OAuthConnectionStore):
        return store
    store = OAuthConnectionStore()
    request.app.state.oauth_connections = store
    return store


async def _get_visible_connection(
    request: Request,
    account_id: str,
    connection_id: UUID,
) -> OAuthConnectionResponse:
    store = _store(request)
    connection = await store.get(account_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    duplicate_id = _duplicate_id(connection.error_message)
    if connection.status == "revoked" and duplicate_id is not None:
        duplicate = await store.get(account_id, duplicate_id)
        if duplicate is not None:
            return response_from_connection(duplicate, is_duplicate=True)
    return response_from_connection(connection)


async def _delete_credentials(request: Request, locator: dict) -> None:
    service = locator.get("service")
    account = locator.get("account")
    if isinstance(service, str) and isinstance(account, str):
        await request.app.state.credential_store.delete(service, account)


def _duplicate_id(message: str | None) -> UUID | None:
    if not isinstance(message, str) or not message.startswith("duplicate:"):
        return None
    try:
        return UUID(message.split(":", 1)[1])
    except ValueError:
        return None
