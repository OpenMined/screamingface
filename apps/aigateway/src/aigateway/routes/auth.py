from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from ipaddress import ip_address
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from tortoise.exceptions import IntegrityError

from ..core.auth.middleware import CurrentAccount
from ..core.errors import AuthError, CredentialNotFoundError
from ..core.oauth.store import (
    OAuthConnectionStore,
    credential_key_for,
)
from ..core.oauth_pkce import generate_pkce, generate_state
from ..core.pending_auth import PendingAuthEntry
from ..core.plugin_base import OAuthCodeExchangeRequest, OAuthConfig
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)

router = APIRouter()


def _index_store(request: Request) -> ProfileIndexStore:
    return _index_store_for_app(request.app)


def _index_store_for_app(app) -> ProfileIndexStore:
    return app.state.profile_index


def _registry(request: Request):
    return _registry_for_app(request.app)


def _registry_for_app(app):
    return app.state.providers


def _credential_store_for_app(app):
    return app.state.credential_store


def _oauth_strategy_for_app(app, plugin, provider: str, account_id: str, name: str):
    return _oauth_strategy_for_credential_name(
        app,
        plugin,
        provider,
        credential_name_for(account_id, name),
    )


def _oauth_strategy_for_credential_name(app, plugin, provider: str, credential_name: str):
    return plugin.oauth_strategy_for(
        credential_name,
        credential_store=_credential_store_for_app(app),
        http_client_factory=getattr(app.state, f"{provider}_http_factory", None),
    )


def _invalidate_profile_session(plugin, account_id: str, name: str) -> None:
    invalidator = getattr(plugin, "invalidate_profile_session", None)
    if callable(invalidator):
        invalidator(credential_name_for(account_id, name))


@asynccontextmanager
async def _profile_refresh_lifecycle(
    request: Request,
    plugin,
    profile: Profile,
    provider: str,
    account_id: str,
    name: str,
) -> AsyncIterator[None]:
    """Shared profile state updates around provider-owned credential refresh."""
    try:
        yield
    except (CredentialNotFoundError, AuthError) as exc:
        profile.state = ProfileState.ERROR
        await _index_store(request).upsert(profile)
        _invalidate_profile_session(plugin, account_id, name)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "message": str(exc),
                "reauth_url": f"/v1/auth/{provider}/profiles/{name}",
            },
        ) from exc
    else:
        profile.state = ProfileState.AUTHENTICATED
        profile.last_refreshed_at = datetime.now(UTC)
        await _index_store(request).upsert(profile)
        _invalidate_profile_session(plugin, account_id, name)


def _pending(request: Request):
    return _pending_for_app(request.app)


def _pending_for_app(app):
    return app.state.pending_auth


def _gateway_redirect_uri_for(request: Request, cfg: OAuthConfig) -> str:
    path = cfg.redirect_path if cfg.redirect_path.startswith("/") else f"/{cfg.redirect_path}"
    port = _request_host_port(request) or request.app.state.settings.port
    return f"http://localhost:{port}{path}"


def _request_host_port(request: Request) -> int | None:
    host_header = request.headers.get("host")
    if host_header:
        try:
            return urlsplit(f"//{host_header.strip()}").port
        except ValueError:
            return None
    return request.url.port


def _loopback_host_allowed(host_header: str | None) -> bool:
    if host_header is None:
        return False
    try:
        hostname = urlsplit(f"//{host_header.strip()}").hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


async def _close_loopback_callback(app, state: str) -> None:
    callbacks = getattr(app.state, "loopback_oauth_callbacks", None)
    if not isinstance(callbacks, dict):
        return
    server = callbacks.pop(state, None)
    if server is None:
        return
    server.close()
    await server.wait_closed()


async def _expire_loopback_callback(app, state: str, ttl_seconds: int) -> None:
    await asyncio.sleep(ttl_seconds)
    await _close_loopback_callback(app, state)


def _http_response(status: int, body: str, *, content_type: str = "text/html") -> bytes:
    reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"}.get(
        status, "Internal Server Error"
    )
    data = body.encode("utf-8")
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"content-type: {content_type}; charset=utf-8\r\n"
        f"content-length: {len(data)}\r\n"
        "connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return headers + data


async def _handle_loopback_callback(
    app,
    provider: str,
    expected_path: str,
    expected_state: str,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    status = 500
    body = "Authentication failed"
    try:
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            status = 400
            body = "Malformed callback request"
            return

        lines = raw.decode("iso-8859-1", errors="replace").split("\r\n")
        request_line = lines[0].split()
        if len(request_line) < 2:
            status = 400
            body = "Malformed callback request"
            return
        method, target = request_line[0], request_line[1]
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        if not _loopback_host_allowed(headers.get("host")):
            status = 403
            body = "Forbidden callback host"
            return

        parsed = urlsplit(target)
        if method != "GET" or parsed.path != expected_path:
            status = 404
            body = "Unknown callback path"
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        if not code or not state:
            status = 400
            body = "Missing callback code or state"
            return
        if state != expected_state:
            status = 400
            body = "OAuth state not recognized or expired"
            return

        await _complete_oauth_for_app(app, provider, code, state)
        status = 200
        body = _CALLBACK_HTML
    except Exception as exc:
        status = 500
        body = (
            "<!doctype html><html><body>"
            "<h2>Authentication failed</h2>"
            f"<p>Provider: {escape(provider)}</p>"
            f"<pre style='white-space:pre-wrap'>{escape(type(exc).__name__)}: "
            f"{escape(str(exc))}</pre>"
            "</body></html>"
        )
    finally:
        writer.write(_http_response(status, body))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await _close_loopback_callback(app, expected_state)


async def _loopback_redirect_uri_for(
    request: Request,
    provider: str,
    cfg: OAuthConfig,
    state: str,
) -> str:
    path = cfg.redirect_path if cfg.redirect_path.startswith("/") else f"/{cfg.redirect_path}"
    callbacks = getattr(request.app.state, "loopback_oauth_callbacks", None)
    if not isinstance(callbacks, dict):
        callbacks = {}
        request.app.state.loopback_oauth_callbacks = callbacks
    for port in cfg.loopback_redirect_ports or []:
        try:
            server = await asyncio.start_server(
                lambda reader, writer: _handle_loopback_callback(
                    request.app, provider, path, state, reader, writer
                ),
                host="localhost",
                port=port,
            )
        except OSError:
            continue
        callbacks = getattr(request.app.state, "loopback_oauth_callbacks", None)
        if not isinstance(callbacks, dict):
            callbacks = {}
            request.app.state.loopback_oauth_callbacks = callbacks
        callbacks[state] = server
        asyncio.create_task(_expire_loopback_callback(request.app, state, 600))
        return f"http://localhost:{port}{path}"
    raise HTTPException(
        status_code=503,
        detail={"code": "oauth_loopback_unavailable", "ports": cfg.loopback_redirect_ports},
    )


async def _redirect_uri_for(
    request: Request,
    provider: str,
    cfg: OAuthConfig,
    state: str,
) -> str:
    if cfg.loopback_redirect_ports:
        return await _loopback_redirect_uri_for(request, provider, cfg, state)
    return _gateway_redirect_uri_for(request, cfg)


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
    for stale_state in _pending(request).pop_for_profile(account_id, provider, body.name):
        await _close_loopback_callback(request.app, stale_state)
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()
    redirect_uri = await _redirect_uri_for(request, provider, cfg, state)

    _pending(request).put(
        state,
        PendingAuthEntry(
            account_id=account_id,
            provider=provider,
            profile_name=body.name,
            profile_id=profile_id,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
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
    authorize_url = f"{cfg.authorize_url}?{urlencode(params)}"

    profile = Profile(
        id=profile_id,
        account_id=account_id,
        provider=provider,
        name=body.name,
        scopes=cfg.scopes,
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

    Some public OAuth clients require a fixed localhost callback path. We
    dispatch to the correct provider by looking up the ``state`` value in the
    pending-auth table.
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


@router.get("/auth/callback")
async def oauth_nested_callback(code: str, state: str, request: Request):
    return await oauth_callback(code, state, request)


@router.get("/oauth2callback")
async def oauth2_loopback_callback(code: str, state: str, request: Request):
    return await oauth_callback(code, state, request)


@router.get("/v1/auth/{provider}/callback")
async def provider_callback(provider: str, code: str, state: str, request: Request):
    """Unauthenticated OAuth callback protected by the pending-auth state nonce."""
    return await _generic_callback(provider, code, state, request)


async def _complete_oauth(
    provider: str,
    code: str,
    state: str,
    request: Request,
    current_account_id: str | None = None,
) -> None:
    await _complete_oauth_for_app(request.app, provider, code, state, current_account_id)


async def _complete_oauth_for_app(
    app,
    provider: str,
    code: str,
    state: str,
    current_account_id: str | None = None,
) -> None:
    """Run the OAuth token exchange and persist credentials.

    Used by both the GET browser-redirect callback and the POST manual
    paste-code endpoint. Raises HTTPException on failure.
    """
    pending_table = _pending_for_app(app)
    pending = pending_table.peek(state)
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

    plugin = _registry_for_app(app).get(provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": provider}
        )

    credential_name = _credential_name_for_pending(pending)
    strategy = _oauth_strategy_for_credential_name(app, plugin, provider, credential_name)
    if strategy is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider_does_not_use_oauth", "provider": provider},
        )

    # Consume the OAuth state after all synchronous validation and before the
    # first await that can race another callback using the same code.
    pending = pending_table.pop(state)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
        )
    try:
        creds = await plugin.exchange_oauth_code(
            OAuthCodeExchangeRequest(
                code=code,
                code_verifier=pending.code_verifier,
                redirect_uri=pending.redirect_uri,
                state=state,
                http_client_factory=getattr(app.state, f"{provider}_http_factory", None),
            )
        )
    except NotImplementedError as exc:
        await _mark_profile_error(app, account_id, provider, name)
        await _mark_connection_error(app, pending, "provider_does_not_use_oauth")
        await _close_loopback_callback(app, state)
        raise HTTPException(
            status_code=400,
            detail={"code": "provider_does_not_use_oauth", "provider": provider},
        ) from exc
    except Exception:
        await _mark_profile_error(app, account_id, provider, name)
        await _mark_connection_error(app, pending, "OAuth code exchange failed")
        await _close_loopback_callback(app, state)
        raise
    if pending.connection_id is None:
        strategy.persist_credentials(creds)
        _invalidate_profile_session(plugin, account_id, name)

    p = await _index_store_for_app(app).get(account_id, provider, name)
    if p is not None:
        p.state = ProfileState.AUTHENTICATED
        label = plugin.account_label_from_credentials(creds)
        if label is not None:
            p.account_label = label
        await _index_store_for_app(app).upsert(p)
    await _record_oauth_connection_completion(app, pending, plugin, creds)
    await _close_loopback_callback(app, state)


def _credential_name_for_pending(pending: PendingAuthEntry) -> str:
    if pending.connection_id is not None:
        return credential_key_for(pending.account_id, pending.connection_id)
    return credential_name_for(pending.account_id, pending.profile_name)


async def _mark_connection_error(app, pending: PendingAuthEntry, message: str) -> None:
    if pending.connection_id is None:
        return
    store = OAuthConnectionStore()
    connection = await store.get(pending.account_id, pending.connection_id)
    if connection is not None:
        await store.mark_error(connection, message)


async def _persist_connection_credentials(
    app,
    plugin,
    provider: str,
    account_id: str,
    connection_id: str,
    creds: dict,
) -> None:
    strategy = _oauth_strategy_for_credential_name(
        app,
        plugin,
        provider,
        credential_key_for(account_id, connection_id),
    )
    if strategy is not None:
        strategy.persist_credentials(creds)


async def _record_oauth_connection_completion(
    app,
    pending: PendingAuthEntry,
    plugin,
    creds: dict,
) -> None:
    store = OAuthConnectionStore()
    extractor = getattr(plugin, "extract_identity", None)
    if not callable(extractor) and pending.connection_id is None:
        return
    identity = (
        await cast(Callable[..., Awaitable[Any]], extractor)(
            creds,
            http_client_factory=getattr(app.state, f"{pending.provider}_http_factory", None),
        )
        if callable(extractor)
        else None
    )
    label = _connection_label(pending, plugin, creds, identity)
    if not label:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_required", "provider": pending.provider},
        )

    duplicate = await store.find_by_identity(
        pending.account_id, pending.provider, getattr(identity, "sub", None)
    )
    if duplicate is not None:
        if pending.connection_id is not None:
            connection = await _connection_for_pending(store, pending, label)
            if duplicate.id != connection.id:
                await store.delete_or_supersede_pending(connection, duplicate)
                _delete_connection_credentials(app, connection.credential_locator)
        return

    if identity is None or identity.sub is None:
        duplicate_label = await store.find_by_label(pending.account_id, pending.provider, label)
        if duplicate_label is not None:
            if pending.connection_id is not None:
                connection = await _connection_for_pending(store, pending, label)
                if duplicate_label.id != connection.id:
                    await store.delete_or_supersede_pending(connection, duplicate_label)
                    _delete_connection_credentials(app, connection.credential_locator)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "label_conflict",
                        "provider": pending.provider,
                        "label": label,
                    },
                )
            return

    connection = await _connection_for_pending(store, pending, label)
    try:
        await store.complete(connection, label=label, identity=identity)
    except IntegrityError as exc:
        await store.mark_revoked(connection, "connection_conflict")
        raise HTTPException(
            status_code=409,
            detail={"code": "connection_conflict", "provider": pending.provider, "label": label},
        ) from exc
    await _persist_connection_credentials(
        app,
        plugin,
        pending.provider,
        pending.account_id,
        str(connection.id),
        creds,
    )


def _delete_connection_credentials(app, locator: dict) -> None:
    service = locator.get("service")
    account = locator.get("account")
    if isinstance(service, str) and isinstance(account, str):
        _credential_store_for_app(app).delete(service, account)


async def _connection_for_pending(
    store: OAuthConnectionStore,
    pending: PendingAuthEntry,
    label: str,
):
    if pending.connection_id is not None:
        connection = await store.get(pending.account_id, pending.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
        return connection
    try:
        return await store.create_pending(
            account_id=pending.account_id,
            provider=pending.provider,
            label=label,
            connection_id=uuid4(),
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_conflict", "provider": pending.provider, "label": label},
        ) from exc


def _connection_label(pending: PendingAuthEntry, plugin, creds: dict, identity) -> str | None:
    if pending.requested_label:
        return pending.requested_label
    if identity is not None:
        label = identity.label()
        if label:
            return label
    label = plugin.account_label_from_credentials(creds)
    if label:
        return label
    return pending.compatibility_profile_name or pending.profile_name


async def _mark_profile_error(app, account_id: str, provider: str, name: str) -> None:
    p = await _index_store_for_app(app).get(account_id, provider, name)
    if p is not None:
        p.state = ProfileState.ERROR
        await _index_store_for_app(app).upsert(p)


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
    authorization code on screen instead of redirecting.
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
    strategy = _oauth_strategy_for_app(request.app, plugin, provider, account_id, name)
    if strategy is not None:
        strategy.delete_credentials()
    _invalidate_profile_session(plugin, account_id, name)
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
    strategy = _oauth_strategy_for_app(request.app, plugin, provider, account_id, name)
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})

    async with _profile_refresh_lifecycle(request, plugin, p, provider, account_id, name):
        await strategy.refresh_credentials()
    return p.model_dump(mode="json")
