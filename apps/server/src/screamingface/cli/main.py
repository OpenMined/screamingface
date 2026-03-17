"""Typer root CLI app — the `sf` command."""

from __future__ import annotations

import logging

import typer

from screamingface.cli.plugin import plugin_app
from screamingface.cli.run import run

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="sf",
    help="ScreamingFace — plugin-based AI ensemble server.",
    no_args_is_help=True,
)

app.command()(run)
app.add_typer(plugin_app, name="plugin")


def _register_plugin_clis() -> None:
    """Discover all plugins and let them register CLI subcommands."""
    from screamingface.core.registry import PluginRegistry
    from screamingface.plugin import Plugin

    registry = PluginRegistry()
    discovered = registry.discover()

    for name, entry in discovered.items():
        try:
            if isinstance(entry, type) and issubclass(entry, Plugin):
                cls = entry
            else:
                cls = entry.load()
            cls.register_cli(app)
        except Exception:
            logger.debug("Failed to register CLI for plugin %r", name, exc_info=True)


_register_plugin_clis()
