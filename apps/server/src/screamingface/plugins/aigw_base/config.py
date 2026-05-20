"""Runtime config resolution for SF's AIGateway integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .settings import AigwBaseSettings, AigwMode

DEFAULT_GATEWAY_URL = "http://127.0.0.1:9105"


@dataclass(frozen=True)
class AigwRuntimeConfig:
    mode: AigwMode
    gateway_url: str
    gateway_url_conflict: bool = False
    deprecated_gateway_urls: tuple[str, ...] = ()

    @property
    def managed_by_runner(self) -> bool:
        return self.mode == "local_managed"


def resolve_aigw_runtime_config(app: Any | None) -> AigwRuntimeConfig:
    """Resolve shared AIGateway settings plus one-release legacy config hints."""

    plugin_config = _plugin_config(app)
    raw_base = _record(plugin_config.get("aigw-base"))
    base_settings = _base_settings(app, raw_base)

    legacy_urls = _backend_local_gateway_urls(plugin_config)
    base_url_explicit = _explicit_base_url(raw_base)
    if base_url_explicit:
        gateway_url = base_settings.gateway_url
        gateway_url_conflict = False
    elif len(legacy_urls) == 1:
        gateway_url = legacy_urls[0]
        gateway_url_conflict = False
    else:
        gateway_url = _legacy_runner_gateway_url(plugin_config) or base_settings.gateway_url
        gateway_url_conflict = len(legacy_urls) > 1

    mode = base_settings.mode
    if not _explicit_base_mode(raw_base):
        mode = _infer_legacy_mode(plugin_config) or mode

    return AigwRuntimeConfig(
        mode=mode,
        gateway_url=gateway_url.rstrip("/"),
        gateway_url_conflict=gateway_url_conflict,
        deprecated_gateway_urls=tuple(legacy_urls),
    )


def gateway_port_from_url(url: str, default: int = 9105) -> int:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return default


def is_runner_disabled() -> bool:
    return os.getenv("SF_AIGW_RUNNER_DISABLED") == "1"


def _base_settings(app: Any | None, raw_base: dict[str, Any]) -> AigwBaseSettings:
    plugin = None
    plugins = getattr(getattr(app, "state", None), "plugins", None)
    if plugins is not None:
        plugin = plugins.active_plugins.get("aigw-base")
    settings = getattr(plugin, "settings", None)
    if isinstance(settings, AigwBaseSettings):
        return settings
    return AigwBaseSettings(**raw_base)


def _plugin_config(app: Any | None) -> dict[str, Any]:
    config = getattr(getattr(app, "state", None), "config", None)
    raw = getattr(config, "plugin_config", {}) if config is not None else {}
    return raw if isinstance(raw, dict) else {}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _backend_local_gateway_urls(plugin_config: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for name, raw in plugin_config.items():
        if not (name.startswith("aigw-") and name.endswith("-backend")):
            continue
        value = _record(raw).get("gateway_url")
        if isinstance(value, str) and value.strip():
            url = value.strip().rstrip("/")
            if url not in urls:
                urls.append(url)
    return urls


def _explicit_base_url(raw_base: dict[str, Any]) -> bool:
    return isinstance(raw_base.get("gateway_url"), str) or "SF_AIGW_BASE__GATEWAY_URL" in os.environ


def _explicit_base_mode(raw_base: dict[str, Any]) -> bool:
    return isinstance(raw_base.get("mode"), str) or "SF_AIGW_BASE__MODE" in os.environ


def _infer_legacy_mode(plugin_config: dict[str, Any]) -> AigwMode | None:
    raw_runner = _record(plugin_config.get("aigw-runner"))
    if raw_runner.get("auth_enabled") is True:
        return "external"
    if raw_runner.get("enabled") is False:
        return "external"
    return None


def _legacy_runner_gateway_url(plugin_config: dict[str, Any]) -> str | None:
    raw_runner = _record(plugin_config.get("aigw-runner"))
    port = raw_runner.get("port")
    if isinstance(port, int) and port > 0 and port != 9105:
        return f"http://127.0.0.1:{port}"
    return None
