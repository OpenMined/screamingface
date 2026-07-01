"""Helpers for routes and plugins that are only safe on local SF binds."""

from __future__ import annotations

import os
from ipaddress import ip_address
from typing import Any

_DEPRECATED_LAN_OVERRIDE_ENV_VARS = ("SF_AIGW_ALLOW_LAN", "SF_BACKEND_API_ALLOW_LAN")


def assert_loopback_bind_host(
    bind_host: str,
    component_name: str,
    *,
    allow_env_vars: tuple[str, ...],
) -> None:
    """Reject non-loopback server binds unless the operator explicitly opts in."""
    if _is_lan_bind_allowed(allow_env_vars):
        return
    normalized = bind_host.strip()
    if normalized and is_loopback_host(normalized):
        return
    env_hint = " or ".join(f"{name}=1" for name in allow_env_vars)
    msg = (
        f"{component_name} refuses to run on non-loopback SF host {bind_host!r}; "
        f"set {env_hint} to override"
    )
    deprecated = [name for name in _DEPRECATED_LAN_OVERRIDE_ENV_VARS if os.environ.get(name) == "1"]
    if deprecated:
        msg += f" ({', '.join(deprecated)} no longer enable LAN binds)"
    raise RuntimeError(msg)


def assert_loopback_server_bind(
    app: Any,
    component_name: str,
    *,
    allow_env_vars: tuple[str, ...],
) -> None:
    """Read ``app.state.config.server.host`` and apply ``assert_loopback_bind_host``."""
    config = getattr(getattr(app, "state", None), "config", None)
    server = getattr(config, "server", None)
    if server is None or not hasattr(server, "host"):
        return
    bind_host = str(getattr(server, "host", "") or "")
    assert_loopback_bind_host(
        bind_host,
        component_name,
        allow_env_vars=allow_env_vars,
    )


def is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_lan_bind_allowed(env_vars: tuple[str, ...]) -> bool:
    return any(os.environ.get(name) == "1" for name in env_vars)
