"""Process-local DNS override via socket.getaddrinfo monkey-patch.

When the intercept plugin modifies /etc/hosts to point intercepted domains
to 127.0.0.1, the server process itself also sees that change. This would
cause the proxy to connect back to itself (routing loop).

This module patches socket.getaddrinfo so that for intercepted domains,
the server resolves to the **real upstream IPs** (captured before /etc/hosts
was modified). All other DNS resolution is unchanged.

The patch is process-local — it only affects the server process. External
processes (like Claude Code) still see the /etc/hosts modification.
"""

from __future__ import annotations

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

_original_getaddrinfo = socket.getaddrinfo
_overrides: dict[str, str] = {}
_patched = False


def install(real_ips: dict[str, str]) -> None:
    """Install the getaddrinfo patch with the given hostname → real-IP mapping."""
    global _patched  # noqa: PLW0603
    _overrides.clear()
    _overrides.update(real_ips)

    if not _patched:
        socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]
        _patched = True
        logger.info("DNS override installed for %s", list(real_ips.keys()))


def uninstall() -> None:
    """Remove the getaddrinfo patch and restore original resolution."""
    global _patched  # noqa: PLW0603
    _overrides.clear()
    if _patched:
        socket.getaddrinfo = _original_getaddrinfo  # type: ignore[assignment]
        _patched = False
        logger.info("DNS override removed")


def _patched_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
    """Resolve intercepted domains to their real IPs, bypass /etc/hosts."""
    hostname = str(host)
    if hostname in _overrides:
        real_ip = _overrides[hostname]
        logger.debug("DNS override: %s → %s", hostname, real_ip)
        return _original_getaddrinfo(real_ip, port, *args, **kwargs)
    return _original_getaddrinfo(host, port, *args, **kwargs)
