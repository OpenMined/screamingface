from __future__ import annotations

import logging
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from tortoise.exceptions import IntegrityError

from aigateway.core.auth.middleware import CurrentAccount
from aigateway.core.credential_strategy_cache import credential_strategy_cache
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth.schemas import (
    CreateApiKeyConnectionRequest,
    CreateOAuthConnectionRequest,
    OAuthConnectionListResponse,
    OAuthConnectionResponse,
    OAuthConnectionTokenResponse,
    PatchOAuthConnectionRequest,
    SetConnectionApiKeyRequest,
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
from aigateway.core.plugin_base import credential_service_provider_for, credential_strategy_from

from .auth import _redirect_uri_for
from .credential_persistence import persist_credentials_or_503

logger = logging.getLogger(__name__)

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


@router.post(
    "/v1/oauth/connections/api-key",
    status_code=201,
    response_model=OAuthConnectionResponse,
)
async def create_api_key_connection(
    body: CreateApiKeyConnectionRequest,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionResponse:
    """Create an api-key-authenticated connection (no OAuth round-trip).

    The key is stored (encrypted at rest) in the same credential-blob slot the
    chat path reads for this connection, so it is usable on a real chat call
    immediately. The key is never echoed back or logged.
    """
    plugin = request.app.state.providers.get(body.provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": body.provider}
        )
    api_key = _validate_api_key(body.api_key)
    account_id = str(current.id)
    connection_id = uuid4()
    # Build the strategy BEFORE creating any row: a provider that does not
    # support api-key auth (codex) yields None here and we 400 without leaving
    # an orphan connection. The credential_name is the same composite key the
    # chat path uses, so persist writes exactly the slot chat reads.
    strategy = credential_strategy_from(
        plugin,
        credential_key_for(account_id, connection_id),
        auth_type="api_key",
        credential_store=request.app.state.credential_store,
    )
    if strategy is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "api_key_not_supported", "provider": body.provider},
        )
    if plugin.requires_oauth_connection_label() and not body.label:
        raise HTTPException(
            status_code=422, detail={"code": "label_required", "provider": body.provider}
        )
    label = body.label or f"api-key-{connection_id}"
    store = _store(request)
    if await store.find_by_label(account_id, body.provider, label) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_conflict", "provider": body.provider, "label": label},
        )
    # Persist the key BEFORE activating the row so a credential-write failure
    # never leaves an active connection with no credential (SF-291 review F4).
    # The blob slot is keyed by the already-generated connection_id — exactly
    # the slot the chat path reads.
    await _persist_api_key_credentials(strategy, api_key)
    try:
        connection = await store.create_api_key(
            account_id=account_id,
            provider=body.provider,
            label=label,
            connection_id=connection_id,
            credential_provider=credential_service_provider_for(plugin, body.provider),
        )
    except Exception as exc:
        # The row could not be created — drop the orphan blob so no credential
        # is left without a connection pointing at it.
        await strategy.delete_credentials()
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=409,
                detail={"code": "label_conflict", "provider": body.provider, "label": label},
            ) from exc
        raise
    credential_strategy_cache(request.app).evict(credential_key_for(account_id, connection_id))
    return response_from_connection(connection)


@router.put(
    "/v1/oauth/connections/{connection_id}/api-key",
    response_model=OAuthConnectionResponse,
)
async def set_connection_api_key(
    connection_id: UUID,
    body: SetConnectionApiKeyRequest,
    request: Request,
    current: CurrentAccount,
) -> OAuthConnectionResponse:
    """Replace the stored API key on an api-key connection.

    Accepts an active OR errored connection: replacing the key is exactly how a
    user recovers a connection that errored on a bad/missing key, so a
    successful replace re-activates it (SF-291 review RF2-1)."""
    account_id = str(current.id)
    store = _store(request)
    connection = await store.get(account_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
    if connection.auth_type != "api_key" or connection.status not in ("active", "error"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "connection_not_api_key",
                "message": "Connection does not use API-key authentication",
            },
        )
    api_key = _validate_api_key(body.api_key)
    plugin = request.app.state.providers.get(connection.provider)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_provider", "provider": connection.provider},
        )
    strategy = credential_strategy_from(
        plugin,
        credential_key_for(account_id, connection.id),
        auth_type="api_key",
        credential_store=request.app.state.credential_store,
    )
    if strategy is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "api_key_not_supported", "provider": connection.provider},
        )
    await _persist_api_key_credentials(strategy, api_key)
    credential_strategy_cache(request.app).evict(credential_key_for(account_id, connection.id))
    # Replacing the key clears any prior error and returns the connection to
    # active (recovery path).
    connection = await store.reactivate(connection)
    return response_from_connection(connection)


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
    if connection.auth_type == "api_key":
        # /refresh is OAuth-only. An api-key connection has nothing to refresh,
        # and running oauth_strategy_for against its blob would raise and flip
        # the row to error (SF-291 review F2). Reject without mutating the row.
        raise HTTPException(status_code=400, detail={"code": "connection_not_oauth"})
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


def _validate_api_key(raw_key: str) -> str:
    """Normalize and length-check a raw API key (the one rule shared verbatim by
    the create and replace endpoints). Raises 400 ``invalid_api_key`` if too
    short. Kept tiny on purpose: each endpoint's provider/strategy resolution
    stays inline because the two flows order those checks differently."""
    api_key = raw_key.strip()
    if len(api_key) < 8:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_api_key", "message": "api_key is missing or too short"},
        )
    return api_key


async def _persist_api_key_credentials(strategy, api_key: str) -> None:
    await persist_credentials_or_503(
        strategy,
        {"auth_type": "api_key", "api_key": api_key},
        description="API-key credentials",
    )


def _duplicate_id(message: str | None) -> UUID | None:
    if not isinstance(message, str) or not message.startswith("duplicate:"):
        return None
    try:
        return UUID(message.split(":", 1)[1])
    except ValueError:
        return None
