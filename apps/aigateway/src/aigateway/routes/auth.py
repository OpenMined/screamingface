from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..core.oauth_pkce import generate_pkce, generate_state
from ..core.pending_auth import PendingAuthEntry
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import Profile, ProfileDefaults, ProfileState
from ..plugins.anthropic_provider import auth as anthropic_auth_module

router = APIRouter()


def _index_store(request: Request) -> ProfileIndexStore:
    return request.app.state.profile_index


def _registry(request: Request):
    return request.app.state.providers


def _pending(request: Request):
    return request.app.state.pending_auth


@router.get("/v1/auth/profiles")
async def list_profiles(request: Request) -> dict:
    idx = await _index_store(request).read()
    return {"profiles": [p.model_dump(mode="json") for p in idx.profiles]}


@router.get("/v1/auth/{provider}/profiles")
async def list_provider_profiles(provider: str, request: Request) -> dict:
    idx = await _index_store(request).read()
    return {"profiles": [p.model_dump(mode="json") for p in idx.profiles if p.provider == provider]}


@router.get("/v1/auth/{provider}/profiles/{name}")
async def get_profile(provider: str, name: str, request: Request) -> dict:
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": name},
        )
    return p.model_dump(mode="json")


class StartAuthRequest(BaseModel):
    name: str
    defaults: ProfileDefaults | None = None


@router.post("/v1/auth/{provider}/profiles", status_code=201)
async def start_oauth(provider: str, body: StartAuthRequest, request: Request) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": provider}
        )

    cfg = plugin.oauth_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})

    profile_id = f"{provider}:{body.name}"
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()

    _pending(request).put(
        state,
        PendingAuthEntry(profile_id=profile_id, code_verifier=code_verifier),
    )

    redirect_uri = f"http://127.0.0.1:{request.app.state.settings.port}{cfg.redirect_path}"
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
    authorize_url = f"{cfg.authorize_url}?{urlencode(params)}"

    profile = Profile(
        id=profile_id,
        provider=provider,
        name=body.name,
        state=ProfileState.PENDING,
        defaults=body.defaults or ProfileDefaults(),
    )
    await _index_store(request).upsert(profile)

    return {
        "profile_id": profile_id,
        "authorize_url": authorize_url,
        "state": state,
        "expires_in": 600,
    }


_CALLBACK_HTML = """<!doctype html>
<html><body><p>Authentication complete. You may close this window.</p></body></html>
"""


@router.get("/v1/auth/anthropic/callback")
async def anthropic_callback(code: str, state: str, request: Request):
    return await _generic_callback("anthropic", code, state, request)


async def _generic_callback(provider: str, code: str, state: str, request: Request):
    pending = _pending(request).pop(state)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
        )

    expected_provider, name = pending.profile_id.split(":", 1)
    if expected_provider != provider:
        raise HTTPException(status_code=400, detail={"code": "provider_mismatch"})

    factory = getattr(request.app.state, f"{provider}_http_factory", None)
    creds = await anthropic_auth_module.exchange_authorization_code(
        code,
        pending.code_verifier,
        http_client_factory=factory,
    )

    plugin = _registry(request).get(provider)
    strategy = plugin.oauth_strategy_for(name)
    # Inject the same credential store as the profile index so tests/fake keychain work.
    if hasattr(strategy, "_store"):
        strategy._store = _index_store(request)._store
    strategy.set_credentials(creds)

    p = await _index_store(request).get(provider, name)
    if p is not None:
        p.state = ProfileState.AUTHENTICATED
        await _index_store(request).upsert(p)

    return HTMLResponse(_CALLBACK_HTML)


@router.get("/v1/auth/{provider}/profiles/{name}/status")
async def profile_status(provider: str, name: str, request: Request) -> dict:
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": name},
        )
    return {
        "state": p.state.value,
        "account_label": p.account_label,
        "last_refreshed_at": p.last_refreshed_at.isoformat() if p.last_refreshed_at else None,
    }


class PatchProfileRequest(BaseModel):
    defaults: ProfileDefaults | None = None
    account_label: str | None = None


@router.patch("/v1/auth/{provider}/profiles/{name}")
async def patch_profile(
    provider: str, name: str, body: PatchProfileRequest, request: Request
) -> dict:
    idx = _index_store(request)
    p = await idx.get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    if body.defaults is not None:
        p.defaults = body.defaults
    if body.account_label is not None:
        p.account_label = body.account_label
    await idx.upsert(p)
    return p.model_dump(mode="json")


@router.delete("/v1/auth/{provider}/profiles/{name}", status_code=204)
async def delete_profile(provider: str, name: str, request: Request):
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    strategy = plugin.oauth_strategy_for(name)
    if strategy is not None and hasattr(strategy, "_store"):
        strategy._store = _index_store(request)._store
        strategy._store.delete(strategy.keychain_service(), strategy.keychain_account())
    await _index_store(request).remove(p.id)


@router.post("/v1/auth/{provider}/profiles/{name}/refresh")
async def refresh_profile(provider: str, name: str, request: Request) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    strategy = plugin.oauth_strategy_for(name)
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})
    await strategy.refresh()
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    return p.model_dump(mode="json")
