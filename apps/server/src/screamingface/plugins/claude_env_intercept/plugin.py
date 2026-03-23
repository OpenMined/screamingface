"""Claude Env Intercept plugin — redirect Claude Code via environment variables.

Zero-sudo alternative to the claude-intercept plugin. Adds ANTHROPIC_BASE_URL
to the shell profile so Claude Code connects through the claude-frontend proxy.
No /etc/hosts, no pfctl, no port 443.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.claude_env_intercept.shellenv import add_exports, remove_exports

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class ClaudeEnvInterceptPlugin(Plugin):
    name = "claude-env-intercept"
    description = "Redirect Claude Code via env vars — no sudo, no /etc/hosts, no port 443"
    depends = ["claude-frontend"]
    conflicts = ["claude-intercept", "mitmproxy-intercept"]

    # Keys that setup() may set via launchctl — needed for cleanup even
    # if the instance that originally set them is long gone.
    _LAUNCHCTL_KEYS = ("ANTHROPIC_BASE_URL",)

    def cleanup_stale(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import has_exports

        if has_exports():
            logger.info("Cleaning up stale claude-env-intercept exports from shell profiles")
            remove_exports()
        # Also unset launchctl vars that may have survived a crash
        if sys.platform == "darwin":
            for key in self._LAUNCHCTL_KEYS:
                try:
                    subprocess.run(
                        ["launchctl", "unsetenv", key],
                        check=False,
                        capture_output=True,
                    )
                except FileNotFoundError:
                    pass

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        # Determine the base URL for Claude Code from claude-frontend settings
        cf_plugin = app.state.plugins.active_plugins.get("claude-frontend")
        if cf_plugin is None or cf_plugin.settings is None:
            raise RuntimeError("claude-env-intercept requires claude-frontend to be active")
        cf_settings = cf_plugin.settings
        base_url = f"http://{cf_settings.listen_host}:{cf_settings.listen_port}"

        # Build env vars
        env_vars: dict[str, str] = {"ANTHROPIC_BASE_URL": base_url}

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
        from screamingface.plugins.claude_env_intercept.cli import claude_env_intercept_app

        app.add_typer(claude_env_intercept_app, name="claude-env-intercept")
