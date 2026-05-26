"""The plugin-audit plugin — exposes `sf plugin-audit deps` via register_cli."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin

if TYPE_CHECKING:
    import typer


class PluginAuditPlugin(Plugin):
    name = "plugin-audit"
    description = "Audit cross-plugin imports vs declared Plugin.depends manifests."
    version = "0.1.0"
    depends: list[str] = []

    @classmethod
    def register_cli(cls, app: typer.Typer) -> None:
        from screamingface.plugins.plugin_audit.cli import plugin_audit_app

        app.add_typer(plugin_audit_app, name="plugin-audit")
