"""Claude Env plugin — redirect Claude Code via environment variables.

Zero-sudo alternative to the intercept plugin. Adds ANTHROPIC_BASE_URL and
NODE_EXTRA_CA_CERTS to the shell profile so Claude Code connects directly
to the ScreamingFace server. No /etc/hosts, no pfctl, no port 443.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_env.shellenv import add_exports, has_exports, remove_exports

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class ClaudeEnvSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_ENV__",
        env_nested_delimiter="__",
    )
    # The URL Claude Code will use to reach this server.
    # Auto-detected from server config if not set explicitly.
    base_url: str | None = None


class ClaudeEnvPlugin(Plugin):
    name = "claude-env"
    description = (
        "Redirect Claude Code via env vars — "
        "no sudo, no /etc/hosts, no port 443"
    )
    depends = ["claude-proxy"]
    settings_class = ClaudeEnvSettings
    system_deps = ["mkcert"]

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason
        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: ClaudeEnvSettings = self.settings  # type: ignore[assignment]

        # Determine the base URL for Claude Code
        base_url = settings.base_url
        if base_url is None:
            cfg = app.state.config
            scheme = "https" if cfg.server.ssl else "http"
            port = cfg.server.port
            base_url = f"{scheme}://localhost:{port}"

        # Find the mkcert root CA
        ca_cert = _mkcert_ca_root()
        if ca_cert is None:
            logger.warning("Could not find mkcert CA root — skipping NODE_EXTRA_CA_CERTS")

        # Build env vars
        env_vars: dict[str, str] = {
            "ANTHROPIC_BASE_URL": base_url,
        }
        if ca_cert is not None:
            env_vars["NODE_EXTRA_CA_CERTS"] = ca_cert

        # Write to shell profile
        add_exports(env_vars)
        logger.info("Claude Code env configured: ANTHROPIC_BASE_URL=%s", base_url)

        # Also set via launchctl for current session (macOS)
        self._launchctl_keys: list[str] = []
        if sys.platform == "darwin":
            for key, value in env_vars.items():
                try:
                    subprocess.run(
                        ["launchctl", "setenv", key, value],
                        check=True,
                        capture_output=True,
                    )
                    self._launchctl_keys.append(key)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        # Register shutdown hook
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    def _unset_launchctl(self) -> None:
        """Remove launchctl env vars set during setup."""
        for key in getattr(self, "_launchctl_keys", []):
            try:
                subprocess.run(
                    ["launchctl", "unsetenv", key],
                    check=True,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    async def _on_shutdown(self) -> None:
        remove_exports()
        self._unset_launchctl()
        logger.info("Claude Code env vars removed from shell profile and launchctl")

    def teardown(self) -> None:
        remove_exports()
        self._unset_launchctl()

    @classmethod
    def register_cli(cls, app: typer.Typer) -> None:
        from screamingface.plugins.claude_env.cli import claude_env_app

        app.add_typer(claude_env_app, name="claude-env")


def _mkcert_ca_root() -> str | None:
    """Return the path to mkcert's root CA certificate, or None."""
    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            capture_output=True,
            text=True,
            check=True,
        )
        from pathlib import Path

        ca_cert = Path(result.stdout.strip()) / "rootCA.pem"
        if ca_cert.exists():
            return str(ca_cert)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None
