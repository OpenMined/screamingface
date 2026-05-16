"""Routes for llm-base — unified backend health status endpoint.

``GET /backends/status`` walks all active backend plugins, calls each
one's ``/health`` endpoint, classifies errors into actionable
categories, and returns a combined JSON response.

This powers the Electron app's Backend Status Panel — the UI that
shows green/yellow/red per provider with [Re-authenticate] buttons.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# How long to wait for each backend's /health response
HEALTH_PROBE_TIMEOUT = 20


def create_router(app: Any = None) -> APIRouter:
    router = APIRouter(tags=["llm-base"])

    @router.get("/backends/status", response_model=None, operation_id="backends_status")
    async def backends_status() -> JSONResponse:
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
        if app is None:
            return JSONResponse(content={}, status_code=200)

        plugins = app.state.plugins.active_plugins
        base_url = _get_base_url(app)

        results: dict[str, Any] = {}
        for plugin in plugins.values():
            if not plugin.backend_call_paths:
                continue
            path = plugin.backend_call_paths[0]
            name = path.lstrip("/")

            health = await _probe_health(base_url, name)
            health["action"] = _classify_action(health)
            health["cli_command"] = _cli_command(plugin, health)
            health["help_text"] = _help_text(plugin, health)
            health["auth_kind"] = _classify_auth_kind(plugin)
            results[name] = health

        return JSONResponse(content=results)

    return router


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
