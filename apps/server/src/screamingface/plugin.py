"""Base Plugin class — the contract every ScreamingFace plugin must implement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from screamingface import __version__

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class PluginSettings(BaseSettings):
    """Base for typed plugin settings. Env vars override init kwargs (sf.json values).

    Priority (highest to lowest): env vars → init kwargs (sf.json) → field defaults.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # env vars first (highest priority), then init kwargs (sf.json), then defaults
        return (env_settings, init_settings, file_secret_settings)


class Plugin:
    """Base class for all ScreamingFace plugins.

    Subclass this and override `setup()` to register hooks, classes, and routes.
    """

    name: str = ""
    # Built-in plugins inherit the package version. External plugins should set their
    # own version via __version__ in their package or override this directly.
    # TODO: integrate with release tooling to auto-bump from pyproject.toml
    version: str = __version__
    depends: list[str] = []
    conflicts: list[str] = []
    description: str = ""
    tags: list[str] = []
    settings_class: type[PluginSettings] | None = None
    system_deps: list[str] = []
    requires_root: bool = False
    required_port: int | None = None
    settings: PluginSettings | None = None

    def preflight(self) -> tuple[bool, str]:
        """Check if this plugin can activate. Return (ok, reason).

        Override this to add custom precondition checks (CLI tools in PATH,
        env vars set, services reachable, etc.). Call super().preflight() first
        to keep the system_deps check.

        Called after settings are resolved but before setup(). If ok is False,
        the plugin is skipped with a console warning showing the reason.
        """
        import shutil

        missing = [dep for dep in self.system_deps if shutil.which(dep) is None]
        if missing:
            return False, f"system tools not found in PATH: {missing}"
        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        """Called when the plugin is activated. Register hooks, classes, and routes here."""

    def teardown(self) -> None:
        """Called when the plugin is deactivated. Clean up resources here."""

    def cleanup_stale(self) -> None:
        """Remove leftover side effects from a previously active instance.

        Called on server startup for discovered-but-inactive plugins. Override
        this in plugins that modify system state (shell profiles, /etc/hosts,
        port forwarding, etc.) so that disabling a plugin reliably cleans up
        even if the server wasn't running when the plugin was removed.
        """

    @classmethod
    def register_cli(cls, app: typer.Typer) -> None:
        """Register CLI subcommands on the root Typer app.

        Called during CLI construction — no server or app instance exists.
        Override this to add plugin-specific CLI commands (e.g. sub-apps).
        """
