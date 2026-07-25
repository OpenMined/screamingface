"""Admin CRUD for global (shared) credential pools.

Used only when the gateway is configured with AIGATEWAY_CREDENTIAL_MODE=shared
(see chat_credentials.py's shared-mode branch); creating pools while the
gateway runs in "byok" mode is still allowed (an admin can provision ahead of
a mode switch) but they are not consulted by chat dispatch until the mode
flips to "shared".
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from aigateway.core.auth.middleware import CurrentAdminAccount
from aigateway.core.credential_pool.models import GlobalCredentialPool
from aigateway.core.credential_pool.schemas import (
    CreateGlobalCredentialPoolRequest,
    GlobalCredentialPoolListResponse,
    GlobalCredentialPoolResponse,
    PatchGlobalCredentialPoolRequest,
)
from aigateway.core.credential_pool.store import (
    GlobalCredentialPoolStore,
    global_pool_credential_key_for,
    global_pool_credential_locator_for,
)
from aigateway.core.plugin_base import credential_strategy_from

from .api_key_validation import normalize_api_key, require_valid_api_key
from .credential_persistence import persist_credentials_or_503

router = APIRouter()


@router.get("/v1/admin/credential-pools", response_model=GlobalCredentialPoolListResponse)
async def list_credential_pools(
    request: Request,
    current: CurrentAdminAccount,
) -> GlobalCredentialPoolListResponse:
    pools = await _store(request).list()
    return GlobalCredentialPoolListResponse(pools=[_response_from_pool(pool) for pool in pools])


@router.get("/v1/admin/credential-pools/{pool_id}", response_model=GlobalCredentialPoolResponse)
async def get_credential_pool(
    pool_id: UUID,
    request: Request,
    current: CurrentAdminAccount,
) -> GlobalCredentialPoolResponse:
    pool = await _store(request).get(pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail={"code": "pool_not_found"})
    return _response_from_pool(pool)


@router.post(
    "/v1/admin/credential-pools",
    status_code=201,
    response_model=GlobalCredentialPoolResponse,
)
async def create_credential_pool(
    body: CreateGlobalCredentialPoolRequest,
    request: Request,
    current: CurrentAdminAccount,
) -> GlobalCredentialPoolResponse:
    plugin = request.app.state.providers.get(body.provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": body.provider}
        )
    api_key = normalize_api_key(body.api_key)
    store = _store(request)
    if await store.get_active_for_provider(body.provider) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "pool_conflict", "provider": body.provider},
        )
    await require_valid_api_key(request, plugin, body.provider, api_key)

    pool = await store.create(
        provider=body.provider,
        auth_type="api_key",
        created_by_id=current.id,
    )
    strategy = credential_strategy_from(
        plugin,
        _pool_credential_name(pool.id),
        auth_type="api_key",
        credential_store=request.app.state.credential_store,
    )
    if strategy is None:
        await store.delete(pool)
        raise HTTPException(
            status_code=400,
            detail={"code": "api_key_not_supported", "provider": body.provider},
        )
    await _persist_pool_api_key(strategy, api_key)
    return _response_from_pool(pool)


@router.patch("/v1/admin/credential-pools/{pool_id}", response_model=GlobalCredentialPoolResponse)
async def patch_credential_pool(
    pool_id: UUID,
    body: PatchGlobalCredentialPoolRequest,
    request: Request,
    current: CurrentAdminAccount,
) -> GlobalCredentialPoolResponse:
    store = _store(request)
    pool = await store.get(pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail={"code": "pool_not_found"})

    if body.api_key is not None:
        plugin = request.app.state.providers.get(pool.provider)
        if plugin is None:
            raise HTTPException(
                status_code=404, detail={"code": "unknown_provider", "provider": pool.provider}
            )
        api_key = normalize_api_key(body.api_key)
        await require_valid_api_key(request, plugin, pool.provider, api_key)
        strategy = credential_strategy_from(
            plugin,
            _pool_credential_name(pool.id),
            auth_type="api_key",
            credential_store=request.app.state.credential_store,
        )
        if strategy is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "api_key_not_supported", "provider": pool.provider},
            )
        await _persist_pool_api_key(strategy, api_key)

    if body.is_active is not None:
        pool = await store.set_active(pool, is_active=body.is_active)
    return _response_from_pool(pool)


@router.delete("/v1/admin/credential-pools/{pool_id}", status_code=204)
async def delete_credential_pool(
    pool_id: UUID,
    request: Request,
    current: CurrentAdminAccount,
) -> None:
    store = _store(request)
    pool = await store.get(pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail={"code": "pool_not_found"})
    locator = global_pool_credential_locator_for(pool.provider, pool.id)
    await request.app.state.credential_store.delete(locator["service"], locator["account"])
    await store.delete(pool)


async def _persist_pool_api_key(strategy, api_key: str) -> None:
    await persist_credentials_or_503(
        strategy,
        {"auth_type": "api_key", "api_key": api_key},
        description="shared credential pool key",
    )


def _store(request: Request) -> GlobalCredentialPoolStore:
    store = getattr(request.app.state, "credential_pools", None)
    if isinstance(store, GlobalCredentialPoolStore):
        return store
    store = GlobalCredentialPoolStore()
    request.app.state.credential_pools = store
    return store


def _pool_credential_name(pool_id: UUID) -> str:
    return global_pool_credential_key_for(pool_id)


def _response_from_pool(pool: GlobalCredentialPool) -> GlobalCredentialPoolResponse:
    return GlobalCredentialPoolResponse(
        id=pool.id,
        provider=pool.provider,
        label=pool.label,
        auth_type=pool.auth_type,
        is_active=pool.is_active,
        created_by_id=pool.created_by_id,
        created_at=pool.created_at,
        updated_at=pool.updated_at,
    )
