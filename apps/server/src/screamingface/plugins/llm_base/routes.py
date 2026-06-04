"""Routes for llm-base — unified backend health status endpoint.

``GET /backends/status`` walks all active backend plugins, calls each
one's ``/health`` endpoint, classifies errors into actionable
categories, and returns a combined JSON response.

This powers the Electron app's Backend Status Panel — the UI that
shows green/yellow/red per provider with [Re-authenticate] buttons.
"""

from __future__ import annotations

import logging
import os
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from screamingface.plugins.aigw_base.client import clear_gateway_session, gateway_session_state
from screamingface.plugins.aigw_base.config import (
    AigwRuntimeConfig,
    is_runner_disabled,
    resolve_aigw_runtime_config,
)

logger = logging.getLogger(__name__)

# How long to wait for each backend's /health response
HEALTH_PROBE_TIMEOUT = 20
STATUS_V2_ACCEPT = "application/vnd.screamingface.backends-status+json;version=2"


def create_router(app: Any = None) -> APIRouter:
    router = APIRouter(tags=["llm-base"])

    @router.get("/backends/status", response_model=None, operation_id="backends_status")
    async def backends_status(request: Request) -> JSONResponse:
        """Unified health status for all active backend plugins.

        Returns a JSON object keyed by backend route name with health info,
        error classification, and actionable hints for the UI.

        Each entry contains:
        - ``authenticated`` (bool)
        - ``model`` (str|null) — the configured default model
        - ``tokens_remaining`` (int|null)
        - ``requests_remaining`` (int|null)
        - ``rate_limit`` (dict) — full rate limit info
        - ``error`` (str|null) — human-readable error
        - ``action`` (str) — UI action: healthy, reauth, rate_limited, degraded
        - ``cli_command`` (str|null) — terminal command to fix the issue
        - ``help_text`` (str|null) — user-facing explanation
        """
        if _wants_status_v2(request):
            return JSONResponse(content=await _build_status_v2(app), status_code=200)

        return JSONResponse(content=await _collect_backend_status(app), status_code=200)

    return router


async def _collect_backend_status(app: Any = None) -> dict[str, Any]:
    if app is None:
        return {}

    plugins = app.state.plugins.active_plugins
    base_url = _get_base_url(app)

    results: dict[str, Any] = {}
    for plugin in plugins.values():
        if not plugin.backend_call_paths:
            continue
        # Only credentialed LLM backends belong in the auth/status sweep. A
        # utility backend (e.g. python-runner) declares backend_call_paths so
        # url4 can route to it but has no gateway provider or CLI auth command,
        # so probing it for credentials is meaningless (404 -> false "reauth").
        if not (
            getattr(plugin, "gateway_provider", None) or getattr(plugin, "cli_auth_command", None)
        ):
            continue
        path = plugin.backend_call_paths[0]
        name = path.lstrip("/")

        health = await _probe_health(base_url, name)
        health["action"] = _classify_action(health)
        health["cli_command"] = _cli_command(plugin, health)
        health["help_text"] = _help_text(plugin, health)
        health["auth_kind"] = _classify_auth_kind(plugin)
        results[name] = health

    return results


def _wants_status_v2(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    explicit = request.headers.get("x-sf-backends-status-version", "")
    return STATUS_V2_ACCEPT in accept or explicit == "2"


async def _build_status_v2(app: Any = None) -> dict[str, Any]:
    if app is None:
        return {"version": 2, "gateway": _empty_gateway(), "action": "gateway_unreachable"}

    config = resolve_aigw_runtime_config(app)
    gateway, gateway_action, message = await _gateway_status(app, config)
    payload: dict[str, Any] = {
        "version": 2,
        "gateway": gateway,
        "action": gateway_action,
    }
    if message:
        payload["message"] = message

    if gateway_action not in {"healthy", "login_provider"}:
        return payload

    backends = await _collect_backend_status(app)
    provider_auth = _provider_auth_status(app, backends)
    if any(p["state"] != "authenticated" for p in provider_auth.values()):
        payload["action"] = "login_provider"
    payload["provider_auth"] = {"providers": provider_auth}
    payload["backends"] = backends
    return payload


async def _gateway_status(
    app: Any,
    config: AigwRuntimeConfig,
) -> tuple[dict[str, Any], str, str | None]:
    gateway = {
        "mode": config.mode,
        "managed_by_runner": config.managed_by_runner and not is_runner_disabled(),
        "reachable": False,
        "authenticated": False,
        "auth_required": config.mode == "external",
        "url": config.gateway_url,
    }
    if config.gateway_url_conflict:
        return (
            gateway,
            "gateway_url_missing",
            "Multiple AIGateway URLs are configured; choose one canonical gateway URL.",
        )
    if is_runner_disabled():
        clear_gateway_session(app)
        return gateway, "gateway_unreachable", "AIGateway runner is disabled."
    if config.mode == "external" and not _external_url_allowed(config.gateway_url):
        return gateway, "gateway_misconfigured", "External AIGateway URL must use HTTPS."

    gateway["reachable"] = await _probe_gateway_healthz(config.gateway_url)
    if not gateway["reachable"]:
        return gateway, "gateway_unreachable" if config.mode == "external" else "starting", None

    if config.mode == "local_managed":
        gateway["authenticated"] = True
        return gateway, "healthy", None

    session = gateway_session_state(app)
    token = session.valid_token()
    if token is not None:
        me_status = await _probe_gateway_me(config.gateway_url, token=token)
        if me_status == 200:
            gateway["authenticated"] = True
            return gateway, "healthy", None
        if me_status == 401:
            clear_gateway_session(app)
            return gateway, "login_gateway", None
        return gateway, "gateway_misconfigured", "AIGateway session check failed."

    me_status = await _probe_gateway_me(config.gateway_url, token=None)
    if me_status == 401:
        return gateway, "login_gateway", None
    if me_status == 200:
        return gateway, "gateway_misconfigured", "External AIGateway has authentication disabled."
    return gateway, "gateway_misconfigured", "AIGateway auth-mode probe failed."


async def _probe_gateway_healthz(gateway_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            resp = await client.get(f"{gateway_url.rstrip('/')}/healthz")
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def _probe_gateway_me(gateway_url: str, *, token: str | None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            resp = await client.get(f"{gateway_url.rstrip('/')}/v1/auth/me", headers=headers)
        return resp.status_code
    except httpx.HTTPError:
        return 0


def _provider_auth_status(app: Any, backends: dict[str, Any]) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for plugin in app.state.plugins.active_plugins.values():
        provider = getattr(plugin, "gateway_provider", None)
        if not provider or not plugin.backend_call_paths:
            continue
        name = plugin.backend_call_paths[0].lstrip("/")
        settings = getattr(plugin, "settings", None)
        profile = getattr(settings, "auth_profile", "default")
        providers[name] = {
            "provider": provider,
            "profile": profile,
            "state": _provider_state(backends.get(name, {})),
        }
    return providers


def _provider_state(health: dict[str, Any]) -> str:
    if health.get("authenticated") is True:
        return "authenticated"
    error = str(health.get("error") or "").lower()
    if "pending" in error or "oauth in progress" in error:
        return "pending"
    if "not found" in error or "not yet created" in error or "profile_not_found" in error:
        return "missing_profile"
    return "error"


def _empty_gateway() -> dict[str, Any]:
    return {
        "mode": "local_managed",
        "managed_by_runner": False,
        "reachable": False,
        "authenticated": False,
        "auth_required": False,
        "url": "http://127.0.0.1:9105",
    }


def _external_url_allowed(gateway_url: str) -> bool:
    if os.getenv("SF_AIGW_ALLOW_INSECURE_EXTERNAL") == "1":
        return True
    parsed = urlparse(gateway_url)
    if parsed.scheme == "https":
        return True
    host = parsed.hostname or ""
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _get_base_url(app: Any) -> str:
    """Get the server's own base URL for internal health probes."""
    config = getattr(app.state, "config", None)
    if config and hasattr(config, "server"):
        host = getattr(config.server, "host", "127.0.0.1")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = getattr(config.server, "port", 8000)
        ssl = getattr(config.server, "ssl", False)
        scheme = "https" if ssl else "http"
        return f"{scheme}://{host}:{port}"
    return "http://127.0.0.1:8000"


async def _probe_health(base_url: str, backend: str) -> dict[str, Any]:
    """Call GET /<backend>/health and return the parsed response."""
    url = f"{base_url}/{backend}/health"
    try:
        async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
            resp = await client.get(url, timeout=HEALTH_PROBE_TIMEOUT)
    except httpx.ConnectError:
        return {
            "authenticated": False,
            "error": f"Connection refused — /{backend}/health unreachable",
        }
    except httpx.TimeoutException:
        return {
            "authenticated": False,
            "error": f"Health probe timed out after {HEALTH_PROBE_TIMEOUT}s",
        }
    except httpx.HTTPError as exc:
        return {"authenticated": False, "error": str(exc)}

    if resp.status_code == 404:
        return {
            "authenticated": False,
            "error": f"/{backend}/health endpoint not found — plugin may not support health checks",
        }

    try:
        return resp.json()
    except Exception:
        return {
            "authenticated": False,
            "error": f"/{backend}/health returned non-JSON (HTTP {resp.status_code})",
        }


def _classify_auth_kind(plugin: Any) -> str:
    """Tells the UI which auth flow to drive when action == 'reauth'.

    - ``"browser"`` — open the gateway-managed authorize URL in a browser
      (used by aigw-*-backend plugins via ``gateway_provider``).
    - ``"cli"``     — spawn a terminal running the plugin's CLI auth
      command.
    """
    if getattr(plugin, "gateway_provider", None):
        return "browser"
    return "cli"


def _classify_action(health: dict[str, Any]) -> str:
    """Classify health status into a UI action category.

    Returns one of:
    - ``healthy``: everything works (green)
    - ``rate_limited``: auth works but rate budget exhausted (red, wait)
    - ``reauth``: credential missing/expired/wrong scopes (yellow, action needed)
    - ``degraded``: auth works but something else is wrong (yellow, info)
    """
    error = (health.get("error") or "").lower()
    authenticated = health.get("authenticated", False)

    if authenticated and not error:
        return "healthy"

    if authenticated and "rate limit" in error:
        return "rate_limited"

    if not authenticated:
        return "reauth"

    # Authenticated but has some other error
    return "degraded"


def _cli_command(plugin: Any, health: dict[str, Any]) -> str | None:
    """Return the terminal command to fix the issue, or None if healthy."""
    action = health.get("action", "")
    if action in ("reauth", "degraded") and not getattr(plugin, "gateway_provider", None):
        command = getattr(plugin, "cli_auth_command", None)
        return command if isinstance(command, str) else None
    return None


def _help_text(plugin: Any, health: dict[str, Any]) -> str | None:
    """Return user-facing help text for the current status."""
    action = health.get("action", "healthy")
    configured = getattr(plugin, "backend_status_help", None)
    if isinstance(configured, dict):
        text = configured.get(action)
        if isinstance(text, str):
            return text

    if action == "rate_limited":
        return "Backend rate limit reached. Capacity will reset automatically."
    if action == "reauth":
        if getattr(plugin, "gateway_provider", None):
            return "OAuth profile is missing or expired. Click Authenticate to open a browser."
        command = getattr(plugin, "cli_auth_command", None)
        if isinstance(command, str):
            return f"Credential is missing or expired. Click Re-authenticate to run '{command}'."
        return "Credential is missing or expired."
    if action == "degraded":
        return "Backend is available but experiencing issues."
    return None
