from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..core.auth.middleware import CurrentAccount
from ..core.oauth_pkce import generate_pkce, generate_state
from ..core.pending_auth import PendingAuthEntry
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from ..plugins.anthropic_provider import auth as anthropic_auth_module

router = APIRouter()


def _index_store(request: Request) -> ProfileIndexStore:
    return request.app.state.profile_index


def _registry(request: Request):
    return request.app.state.providers


def _pending(request: Request):
    return request.app.state.pending_auth


@router.get("/v1/auth/profiles")
async def list_profiles(request: Request, current: CurrentAccount) -> dict:
    profiles = await _index_store(request).list(str(current.id))
    return {"profiles": [p.model_dump(mode="json") for p in profiles]}


@router.get("/v1/auth/{provider}/profiles")
async def list_provider_profiles(provider: str, request: Request, current: CurrentAccount) -> dict:
    profiles = await _index_store(request).list(str(current.id), provider)
    return {"profiles": [p.model_dump(mode="json") for p in profiles]}


@router.get("/v1/auth/{provider}/profiles/{name}")
async def get_profile(provider: str, name: str, request: Request, current: CurrentAccount) -> dict:
    p = await _index_store(request).get(str(current.id), provider, name)
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
async def start_oauth(
    provider: str,
    body: StartAuthRequest,
    request: Request,
    current: CurrentAccount,
) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": provider}
        )

    cfg = plugin.oauth_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})

    account_id = str(current.id)
    profile_id = profile_id_for(account_id, provider, body.name)
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()

    _pending(request).put(
        state,
        PendingAuthEntry(
            account_id=account_id,
            provider=provider,
            profile_name=body.name,
            profile_id=profile_id,
            code_verifier=code_verifier,
        ),
    )

    # The Claude Code public OAuth client (and similar public clients) only
    # accept ``http://localhost:*/callback`` as a redirect URI — using
    # ``127.0.0.1`` or any path other than ``/callback`` triggers an
    # "Authorization failed" error from claude.ai. We use ``localhost`` and
    # the top-level ``/callback`` route (provider is dispatched via state).
    redirect_uri = f"http://localhost:{request.app.state.settings.port}/callback"
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
        account_id=account_id,
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


@router.get("/callback")
async def oauth_callback(code: str, state: str, request: Request):
    """Provider-agnostic OAuth callback.

    This route intentionally does not require a JWT because OAuth providers
    redirect browser tabs here after the user leaves the app. The pending-auth
    state nonce is the callback credential; it maps back to the initiating
    account and profile.

    Anthropic's public Claude Code OAuth client (and most OAuth providers
    using public clients) only accepts ``http://localhost:*/callback`` as
    the redirect URI — i.e. the path is fixed at ``/callback`` and is not
    namespaced per provider. We dispatch to the correct provider by
    looking up the ``state`` value in the pending-auth table.
    """
    pending_entry = _pending(request).peek(state)
    if pending_entry is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
        )
    provider = pending_entry.provider
    try:
        return await _generic_callback(provider, code, state, request)
    except Exception as exc:
        # Surface a readable error in the browser tab so the user sees what
        # went wrong (instead of a generic 500). Most failures here are
        # token-endpoint mismatches; the message is helpful for debugging.
        return HTMLResponse(
            f"<!doctype html><html><body>"
            f"<h2>Authentication failed</h2>"
            f"<p>Provider: {escape(provider)}</p>"
            f"<pre style='white-space:pre-wrap'>{escape(type(exc).__name__)}: "
            f"{escape(str(exc))}</pre>"
            f"</body></html>",
            status_code=500,
        )


# Back-compat: older OAuth flows (and tests) still use the per-provider path.
@router.get("/v1/auth/anthropic/callback")
async def anthropic_callback(code: str, state: str, request: Request):
    """Unauthenticated OAuth callback protected by the pending-auth state nonce."""
    return await _generic_callback("anthropic", code, state, request)


async def _complete_oauth(
    provider: str,
    code: str,
    state: str,
    request: Request,
    current_account_id: str | None = None,
) -> None:
    """Run the OAuth token exchange and persist credentials.

    Used by both the GET browser-redirect callback and the POST manual
    paste-code endpoint. Raises HTTPException on failure.
    """
    pending = _pending(request).peek(state)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
        )

    if pending.provider != provider:
        raise HTTPException(status_code=400, detail={"code": "provider_mismatch"})
    account_id = pending.account_id
    if current_account_id is not None and current_account_id != account_id:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    name = pending.profile_name

    factory = getattr(request.app.state, f"{provider}_http_factory", None)
    # Must match the redirect_uri sent to /authorize. Both the start-OAuth
    # route and this exchange use the same canonical localhost+/callback
    # form so Anthropic's redirect-URI check passes.
    redirect_uri = f"http://localhost:{request.app.state.settings.port}/callback"
    creds = await anthropic_auth_module.exchange_authorization_code(
        code,
        pending.code_verifier,
        redirect_uri=redirect_uri,
        state=state,
        http_client_factory=factory,
    )

    plugin = _registry(request).get(provider)
    strategy = plugin.oauth_strategy_for(credential_name_for(account_id, name))
    # Inject the same credential store as the profile index so tests/fake keychain work.
    if hasattr(strategy, "_store"):
        strategy._store = _index_store(request)._store
    strategy.set_credentials(creds)

    p = await _index_store(request).get(account_id, provider, name)
    if p is not None:
        p.state = ProfileState.AUTHENTICATED
        await _index_store(request).upsert(p)
    _pending(request).pop(state)


async def _generic_callback(provider: str, code: str, state: str, request: Request):
    await _complete_oauth(provider, code, state, request)
    return HTMLResponse(_CALLBACK_HTML)


class ExchangeCodeRequest(BaseModel):
    code: str
    state: str


@router.post("/v1/auth/{provider}/exchange-code")
async def exchange_code(
    provider: str,
    body: ExchangeCodeRequest,
    request: Request,
    current: CurrentAccount,
) -> dict:
    """Manual paste-code path for OAuth flows where the provider shows the
    authorization code on screen instead of redirecting (e.g. claude.ai/oauth
    with `code=true`).
    """
    await _complete_oauth(provider, body.code, body.state, request, str(current.id))
    return {"state": "authenticated"}


@router.get("/v1/auth/{provider}/profiles/{name}/status")
async def profile_status(
    provider: str, name: str, request: Request, current: CurrentAccount
) -> dict:
    p = await _index_store(request).get(str(current.id), provider, name)
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
    provider: str,
    name: str,
    body: PatchProfileRequest,
    request: Request,
    current: CurrentAccount,
) -> dict:
    idx = _index_store(request)
    p = await idx.get(str(current.id), provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    if body.defaults is not None:
        p.defaults = body.defaults
    if body.account_label is not None:
        p.account_label = body.account_label
    await idx.upsert(p)
    return p.model_dump(mode="json")


@router.delete("/v1/auth/{provider}/profiles/{name}", status_code=204)
async def delete_profile(provider: str, name: str, request: Request, current: CurrentAccount):
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    account_id = str(current.id)
    p = await _index_store(request).get(account_id, provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    strategy = plugin.oauth_strategy_for(credential_name_for(account_id, name))
    if strategy is not None and hasattr(strategy, "_store"):
        strategy._store = _index_store(request)._store
        strategy._store.delete(strategy.keychain_service(), strategy.keychain_account())
    await _index_store(request).remove(p.id)


@router.post("/v1/auth/{provider}/profiles/{name}/refresh")
async def refresh_profile(
    provider: str, name: str, request: Request, current: CurrentAccount
) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    account_id = str(current.id)
    p = await _index_store(request).get(account_id, provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    strategy = plugin.oauth_strategy_for(credential_name_for(account_id, name))
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})
    await strategy.refresh()
    return p.model_dump(mode="json")
