"""The `sf plugin` subcommands — list, info, enable, disable."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

plugin_app = typer.Typer(help="Manage ScreamingFace plugins.")


@plugin_app.command("list")
def plugin_list() -> None:
    """Show all discovered plugins and their activation state."""
    from screamingface.core.config import load_config
    from screamingface.core.registry import PluginRegistry

    config = load_config()
    registry = PluginRegistry()
    discovered = registry.discover()

    if not discovered:
        typer.echo("No plugins discovered.")
        return

    enabled_set = set(config.plugins)
    for name, ep in sorted(discovered.items()):
        state = "enabled" if name in enabled_set else "available"
        typer.echo(f"  {name:<30} [{state}]  ({ep.value})")


@plugin_app.command("info")
def plugin_info(
    name: Annotated[str, typer.Argument(help="Plugin name")],
) -> None:
    """Show details about a specific plugin."""
    from screamingface.core.registry import PluginRegistry

    registry = PluginRegistry()
    registry.discover()

    if name not in registry.discovered_plugins:
        typer.echo(f"Plugin {name!r} not found.")
        raise typer.Exit(1)

    plugin = registry.load_plugin(name)
    typer.echo(f"Name:        {plugin.name}")
    typer.echo(f"Version:     {plugin.version}")
    typer.echo(f"Description: {plugin.description}")
    typer.echo(f"Depends:     {', '.join(plugin.depends) or '(none)'}")


@plugin_app.command("enable")
def plugin_enable(
    name: Annotated[str, typer.Argument(help="Plugin name to enable")],
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path"),
    ] = None,
) -> None:
    """Enable a plugin by adding it to sf.json."""
    from screamingface.core.config import load_config, save_config

    config = load_config(config_path)
    if name not in config.plugins:
        config.plugins.append(name)
        save_config(config, config_path)
        typer.echo(f"Enabled plugin: {name}")
    else:
        typer.echo(f"Plugin {name!r} is already enabled.")


@plugin_app.command("disable")
def plugin_disable(
    name: Annotated[str, typer.Argument(help="Plugin name to disable")],
    config_path: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path"),
    ] = None,
) -> None:
    """Disable a plugin by removing it from sf.json."""
    from screamingface.core.config import load_config, save_config

    config = load_config(config_path)
    if name in config.plugins:
        config.plugins.remove(name)
        save_config(config, config_path)
        typer.echo(f"Disabled plugin: {name}")
    else:
        typer.echo(f"Plugin {name!r} is not enabled.")
