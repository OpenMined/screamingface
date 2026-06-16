from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
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
from ..core.credential_strategy_cache import credential_strategy_cache
from ..core.errors import AuthError, CredentialNotFoundError
from ..core.oauth.store import (
    OAuthConnectionStore,
    credential_key_for,
)
from ..core.oauth_pkce import generate_pkce, generate_state
from ..core.pending_auth import PendingAuthEntry
from ..core.plugin_base import (
    OAuthCodeExchangeRequest,
    OAuthConfig,
    credential_service_provider_for,
    credential_strategy_from,
)
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import (
    AuthType,
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)

router = APIRouter()


@dataclass(frozen=True)
class _LoopbackHttpRequest:
    method: str
    target: str
    headers: dict[str, str]


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


def _credential_strategy_for_app(
    app,
    plugin,
    provider: str,
    account_id: str,
    name: str,
    auth_type: AuthType = "oauth",
):
    return _credential_strategy_for_credential_name(
        app,
        plugin,
        provider,
        credential_name_for(account_id, name),
        auth_type=auth_type,
    )


def _credential_strategy_for_credential_name(
    app,
    plugin,
    provider: str,
    credential_name: str,
    auth_type: AuthType = "oauth",
):
    return credential_strategy_from(
        plugin,
        credential_name,
        auth_type=auth_type,
        credential_store=_credential_store_for_app(app),
        http_client_factory=getattr(app.state, f"{provider}_http_factory", None),
    )


def _invalidate_profile_session(app, plugin, account_id: str, name: str) -> None:
    credential_name = credential_name_for(account_id, name)
    invalidator = getattr(plugin, "invalidate_profile_session", None)
    if callable(invalidator):
        invalidator(credential_name)
    # Drop the shared cached strategy so re-auth / api-key change / delete / refresh
    # never serve a stale in-memory token from a prior credential (SF-282).
    credential_strategy_cache(app).evict(credential_name)


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
        _invalidate_profile_session(request.app, plugin, account_id, name)
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
        _invalidate_profile_session(request.app, plugin, account_id, name)


def _pending(request: Request):
    return _pending_for_app(request.app)


def _pending_for_app(app):
    return app.state.pending_auth


def _redirect_path_for(cfg: OAuthConfig) -> str:
    return cfg.redirect_path if cfg.redirect_path.startswith("/") else f"/{cfg.redirect_path}"


def _gateway_redirect_uri_for(request: Request, cfg: OAuthConfig) -> str:
    path = _redirect_path_for(cfg)
    public_url = request.app.state.settings.public_url
    if public_url:
        return f"{public_url}{path}"
    port = _request_host_port(request) or request.app.state.settings.port
    return f"http://localhost:{port}{path}"


def _invalid_redirect_uri(provider: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "invalid_redirect_uri", "provider": provider, "message": message},
    )


def _validate_redirect_uri_override(
    provider: str,
    cfg: OAuthConfig,
    redirect_uri: str,
) -> str:
    try:
        parsed = urlsplit(redirect_uri)
        port = parsed.port
    except ValueError as exc:
        raise _invalid_redirect_uri(provider, "redirect_uri is not a valid URL") from exc

    if parsed.scheme != "http":
        raise _invalid_redirect_uri(provider, "redirect_uri must use http")
    if parsed.username is not None or parsed.password is not None:
        raise _invalid_redirect_uri(provider, "redirect_uri must not include credentials")
    if parsed.query or parsed.fragment:
        raise _invalid_redirect_uri(provider, "redirect_uri must not include query or fragment")
    if port is None or port < 1:
        raise _invalid_redirect_uri(provider, "redirect_uri must include a valid port")

    hostname = (parsed.hostname or "").lower()
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise _invalid_redirect_uri(provider, "redirect_uri host must be loopback localhost")

    expected_path = _redirect_path_for(cfg)
    if parsed.path != expected_path:
        raise _invalid_redirect_uri(
            provider,
            f"redirect_uri path must be {expected_path}",
        )

    allowed_ports = cfg.loopback_redirect_ports
    if allowed_ports and port not in allowed_ports:
        raise _invalid_redirect_uri(
            provider,
            f"redirect_uri port must be one of {allowed_ports}",
        )
    return redirect_uri


def _request_host_port(request: Request) -> int | None:
    host_header = request.headers.get("host")
    if host_header:
        try:
            return urlsplit(f"//{host_header.strip()}").port
        except ValueError:
            return None
    return request.url.port


def _loopback_host_allowed(host_header: str | None) -> bool:
    hostname = _loopback_hostname(host_header)
    if hostname is None:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _loopback_hostname(host_header: str | None) -> str | None:
    if host_header is None:
        return None
    try:
        return urlsplit(f"//{host_header.strip()}").hostname
    except ValueError:
        return None


async def _close_loopback_callback(app, state: str) -> None:
    callbacks = getattr(app.state, "loopback_oauth_callbacks", None)
    server = callbacks.pop(state, None) if isinstance(callbacks, dict) else None
    tasks = getattr(app.state, "loopback_oauth_callback_tasks", None)
    task = tasks.pop(state, None) if isinstance(tasks, dict) else None
    current_task = asyncio.current_task()
    if task is not None and task is not current_task:
        task.cancel()
    if server is not None:
        server.close()
        await server.wait_closed()
    if task is not None and task is not current_task:
        await asyncio.gather(task, return_exceptions=True)


async def close_loopback_callbacks(app) -> None:
    callbacks = getattr(app.state, "loopback_oauth_callbacks", None)
    servers = list(callbacks.values()) if isinstance(callbacks, dict) else []
    if isinstance(callbacks, dict):
        callbacks.clear()

    task_map = getattr(app.state, "loopback_oauth_callback_tasks", None)
    tasks = list(task_map.values()) if isinstance(task_map, dict) else []
    if isinstance(task_map, dict):
        task_map.clear()

    current_task = asyncio.current_task()
    tasks_to_cancel = [task for task in tasks if task is not current_task]
    for task in tasks_to_cancel:
        task.cancel()
    for server in servers:
        server.close()
    if tasks_to_cancel:
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
    for server in servers:
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


async def _read_loopback_http_request(
    reader: asyncio.StreamReader,
) -> _LoopbackHttpRequest | None:
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
        return None
    return _parse_loopback_http_request(raw)


def _parse_loopback_http_request(raw: bytes) -> _LoopbackHttpRequest | None:
    lines = raw.decode("iso-8859-1", errors="replace").split("\r\n")
    request_line = lines[0].split()
    if len(request_line) < 2:
        return None
    return _LoopbackHttpRequest(
        method=request_line[0],
        target=request_line[1],
        headers=_parse_loopback_headers(lines[1:]),
    )


def _parse_loopback_headers(lines: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in lines:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


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
    close_callback = False
    try:
        callback_request = await _read_loopback_http_request(reader)
        if callback_request is None:
            status = 400
            body = "Malformed callback request"
            return

        if not _loopback_host_allowed(callback_request.headers.get("host")):
            status = 403
            body = "Forbidden callback host"
            return

        parsed = urlsplit(callback_request.target)
        if callback_request.method != "GET" or parsed.path != expected_path:
            status = 404
            body = "Unknown callback path"
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        close_callback = state == expected_state
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
        if close_callback:
            await _close_loopback_callback(app, expected_state)


async def _loopback_redirect_uri_for(
    request: Request,
    provider: str,
    cfg: OAuthConfig,
    state: str,
) -> str:
    path = _redirect_path_for(cfg)
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
        tasks = getattr(request.app.state, "loopback_oauth_callback_tasks", None)
        if not isinstance(tasks, dict):
            tasks = {}
            request.app.state.loopback_oauth_callback_tasks = tasks
        tasks[state] = asyncio.create_task(_expire_loopback_callback(request.app, state, 600))
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
    redirect_uri: str | None = None,
) -> str:
    if redirect_uri is not None:
        return _validate_redirect_uri_override(provider, cfg, redirect_uri)
    if request.app.state.settings.public_url:
        return _gateway_redirect_uri_for(request, cfg)
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
    redirect_uri: str | None = None


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
    redirect_uri: str | None = None
    if body.redirect_uri is not None:
        redirect_uri = await _redirect_uri_for(request, provider, cfg, state, body.redirect_uri)
    for stale_state in _pending(request).pop_for_profile(account_id, provider, body.name):
        await _close_loopback_callback(request.app, stale_state)
    if redirect_uri is None:
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

    # Update the existing profile in place instead of replacing it wholesale:
    # an api_key profile keeps its auth_type/account_label/defaults until the
    # OAuth flow actually COMPLETES (completion flips auth_type to "oauth" in
    # _mark_profile_authenticated). A wholesale reset at flow start would
    # desync the index from the still-stored API-key blob (SF-244 audit F08).
    profile = await _index_store(request).get(account_id, provider, body.name)
    if profile is None:
        profile = Profile(
            id=profile_id,
            account_id=account_id,
            provider=provider,
            name=body.name,
        )
    profile.scopes = list(cfg.scopes)
    profile.state = ProfileState.PENDING
    if body.defaults is not None:
        profile.defaults = body.defaults
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
    pending = _pending_or_unknown(pending_table.peek(state))
    _validate_pending_oauth(pending, provider, current_account_id)
    plugin = _registry_for_app(app).get(provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": provider}
        )

    credential_name = _credential_name_for_pending(pending)
    strategy = _credential_strategy_for_credential_name(app, plugin, provider, credential_name)
    if strategy is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "provider_does_not_use_oauth", "provider": provider},
        )

    # Consume the OAuth state after all synchronous validation and before the
    # first await that can race another callback using the same code.
    pending = _pending_or_unknown(pending_table.pop(state))
    try:
        creds = await _exchange_oauth_code_for_pending(app, plugin, provider, code, state, pending)
    except NotImplementedError as exc:
        await _mark_oauth_completion_error(app, pending, "provider_does_not_use_oauth", state)
        raise HTTPException(
            status_code=400,
            detail={"code": "provider_does_not_use_oauth", "provider": provider},
        ) from exc
    except Exception:
        await _mark_oauth_completion_error(app, pending, "OAuth code exchange failed", state)
        raise
    if pending.connection_id is None:
        await strategy.persist_credentials(creds)
        _invalidate_profile_session(app, plugin, pending.account_id, pending.profile_name)

    await _mark_profile_authenticated(app, pending, plugin, creds)
    await _record_oauth_connection_completion(app, pending, plugin, creds)
    await _close_loopback_callback(app, state)


def _pending_or_unknown(pending: PendingAuthEntry | None) -> PendingAuthEntry:
    if pending is not None:
        return pending
    raise HTTPException(
        status_code=400,
        detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
    )


def _validate_pending_oauth(
    pending: PendingAuthEntry,
    provider: str,
    current_account_id: str | None,
) -> None:
    if pending.provider != provider:
        raise HTTPException(status_code=400, detail={"code": "provider_mismatch"})
    if current_account_id is not None and current_account_id != pending.account_id:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})


async def _exchange_oauth_code_for_pending(
    app,
    plugin,
    provider: str,
    code: str,
    state: str,
    pending: PendingAuthEntry,
) -> dict:
    return await plugin.exchange_oauth_code(
        OAuthCodeExchangeRequest(
            code=code,
            code_verifier=pending.code_verifier,
            redirect_uri=pending.redirect_uri,
            state=state,
            http_client_factory=getattr(app.state, f"{provider}_http_factory", None),
        )
    )


async def _mark_oauth_completion_error(
    app,
    pending: PendingAuthEntry,
    connection_message: str,
    state: str,
) -> None:
    await _mark_profile_error(app, pending.account_id, pending.provider, pending.profile_name)
    await _mark_connection_error(app, pending, connection_message)
    await _close_loopback_callback(app, state)


async def _mark_profile_authenticated(app, pending: PendingAuthEntry, plugin, creds: dict) -> None:
    profile = await _index_store_for_app(app).get(
        pending.account_id,
        pending.provider,
        pending.profile_name,
    )
    if profile is None:
        return
    profile.state = ProfileState.AUTHENTICATED
    # A completed OAuth round-trip overwrites the credential slot, so the
    # discriminator must flip back even if the profile was api_key before.
    profile.auth_type = "oauth"
    label = plugin.account_label_from_credentials(creds)
    if label is not None:
        profile.account_label = label
    await _index_store_for_app(app).upsert(profile)


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
    credential_strategy_cache(app).evict(
        credential_key_for(pending.account_id, pending.connection_id)
    )


async def _persist_connection_credentials(
    app,
    plugin,
    provider: str,
    account_id: str,
    connection_id: str,
    creds: dict,
) -> None:
    strategy = _credential_strategy_for_credential_name(
        app,
        plugin,
        provider,
        credential_key_for(account_id, connection_id),
    )
    if strategy is not None:
        await strategy.persist_credentials(creds)
    credential_strategy_cache(app).evict(credential_key_for(account_id, connection_id))


async def _record_oauth_connection_completion(
    app,
    pending: PendingAuthEntry,
    plugin,
    creds: dict,
) -> None:
    store = OAuthConnectionStore()
    if not _plugin_extracts_identity(plugin) and pending.connection_id is None:
        return
    identity = await _extract_connection_identity(app, pending, plugin, creds)
    label = _connection_label(pending, plugin, creds, identity)
    if not label:
        raise HTTPException(
            status_code=409,
            detail={"code": "label_required", "provider": pending.provider},
        )

    if await _handle_duplicate_connection_identity(app, store, pending, plugin, label, identity):
        return
    if await _handle_duplicate_connection_label(app, store, pending, plugin, label, identity):
        return

    connection = await _connection_for_pending(store, pending, plugin, label)
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


def _plugin_extracts_identity(plugin) -> bool:
    return callable(getattr(plugin, "extract_identity", None))


async def _extract_connection_identity(
    app,
    pending: PendingAuthEntry,
    plugin,
    creds: dict,
) -> Any | None:
    extractor = getattr(plugin, "extract_identity", None)
    if not callable(extractor):
        return None
    return await cast(Callable[..., Awaitable[Any]], extractor)(
        creds,
        http_client_factory=getattr(app.state, f"{pending.provider}_http_factory", None),
    )


async def _handle_duplicate_connection_identity(
    app,
    store: OAuthConnectionStore,
    pending: PendingAuthEntry,
    plugin,
    label: str,
    identity,
) -> bool:
    duplicate = await store.find_by_identity(
        pending.account_id, pending.provider, getattr(identity, "sub", None)
    )
    if duplicate is None:
        return False
    if pending.connection_id is not None:
        connection = await _connection_for_pending(store, pending, plugin, label)
        if duplicate.id != connection.id:
            await store.delete_or_supersede_pending(connection, duplicate)
            await _delete_connection_credentials(app, connection.credential_locator)
    return True


async def _handle_duplicate_connection_label(
    app,
    store: OAuthConnectionStore,
    pending: PendingAuthEntry,
    plugin,
    label: str,
    identity,
) -> bool:
    if identity is not None and identity.sub is not None:
        return False
    duplicate_label = await store.find_by_label(pending.account_id, pending.provider, label)
    if duplicate_label is None:
        return False
    if pending.connection_id is None:
        return True
    connection = await _connection_for_pending(store, pending, plugin, label)
    if duplicate_label.id != connection.id:
        await store.delete_or_supersede_pending(connection, duplicate_label)
        await _delete_connection_credentials(app, connection.credential_locator)
    raise HTTPException(
        status_code=409,
        detail={"code": "label_conflict", "provider": pending.provider, "label": label},
    )


async def _delete_connection_credentials(app, locator: dict) -> None:
    service = locator.get("service")
    account = locator.get("account")
    if isinstance(service, str) and isinstance(account, str):
        await _credential_store_for_app(app).delete(service, account)


async def _connection_for_pending(
    store: OAuthConnectionStore,
    pending: PendingAuthEntry,
    plugin,
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
            credential_provider=credential_service_provider_for(plugin, pending.provider),
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
        "auth_type": p.auth_type,
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


class SetApiKeyRequest(BaseModel):
    api_key: str
    defaults: ProfileDefaults | None = None


@router.put("/v1/auth/{provider}/profiles/{name}/api-key")
async def set_profile_api_key(
    provider: str,
    name: str,
    body: SetApiKeyRequest,
    request: Request,
    current: CurrentAccount,
) -> dict:
    """Create or update a profile that authenticates with a raw API key.

    No OAuth round-trip: the profile is AUTHENTICATED as soon as the key is
    stored. The key is persisted to the profile's credential blob slot (so a
    later OAuth completion overwrites it, and delete removes it) and is never
    echoed back in responses or logs.
    """
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(
            status_code=404, detail={"code": "unknown_provider", "provider": provider}
        )
    api_key = body.api_key.strip()
    if len(api_key) < 8:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_api_key", "message": "api_key is missing or too short"},
        )
    account_id = str(current.id)
    strategy = _credential_strategy_for_app(
        request.app, plugin, provider, account_id, name, auth_type="api_key"
    )
    if strategy is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "api_key_not_supported", "provider": provider},
        )

    # Cancel any in-flight OAuth flow for this profile: a late callback
    # (pending TTL is 600s) would otherwise silently overwrite the key we are
    # about to store (SF-244 audit F10). Mirrors start_oauth's stale cleanup.
    for stale_state in _pending(request).pop_for_profile(account_id, provider, name):
        await _close_loopback_callback(request.app, stale_state)

    idx = _index_store(request)
    profile = await idx.get(account_id, provider, name)
    if profile is None:
        profile = Profile(
            id=profile_id_for(account_id, provider, name),
            account_id=account_id,
            provider=provider,
            name=name,
        )
    if body.defaults is not None:
        profile.defaults = body.defaults
    profile.auth_type = "api_key"
    profile.state = ProfileState.AUTHENTICATED
    profile.last_refreshed_at = datetime.now(UTC)
    profile.account_label = f"API key ····{api_key[-4:]}"
    profile.scopes = []  # OAuth scopes are meaningless for API-key auth (F24)

    await strategy.persist_credentials({"auth_type": "api_key", "api_key": api_key})
    await idx.upsert(profile)
    _invalidate_profile_session(request.app, plugin, account_id, name)
    return profile.model_dump(mode="json")


@router.delete("/v1/auth/{provider}/profiles/{name}", status_code=204)
async def delete_profile(provider: str, name: str, request: Request, current: CurrentAccount):
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    account_id = str(current.id)
    p = await _index_store(request).get(account_id, provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    strategy = _credential_strategy_for_app(
        request.app, plugin, provider, account_id, name, auth_type=p.auth_type
    )
    if strategy is not None:
        await strategy.delete_credentials()
    _invalidate_profile_session(request.app, plugin, account_id, name)
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
    strategy = _credential_strategy_for_app(
        request.app, plugin, provider, account_id, name, auth_type=p.auth_type
    )
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})

    async with _profile_refresh_lifecycle(request, plugin, p, provider, account_id, name):
        await strategy.refresh_credentials()
    return p.model_dump(mode="json")
