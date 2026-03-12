"""The `sf plugin` subcommands — list, info, enable, disable."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

plugin_app = typer.Typer(help="Manage ScreamingFace plugins.")


@plugin_app.command("list")
def plugin_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show all discovered plugins and their activation state."""
    import json

    from screamingface.core.config import load_config
    from screamingface.core.registry import PluginRegistry

    config = load_config()
    registry = PluginRegistry()
    discovered = registry.discover()

    if not discovered:
        if json_output:
            typer.echo("{}")
        else:
            typer.echo("No plugins discovered.")
        return

    enabled_set = set(config.plugins)

    if json_output:
        result = {}
        for name, entry in sorted(discovered.items()):
            plugin = registry.load_plugin(name)
            result[name] = {
                "state": "enabled" if name in enabled_set else "available",
                "version": plugin.version if plugin else None,
                "description": plugin.description if plugin else None,
            }
        typer.echo(json.dumps(result))
        return

    for name, entry in sorted(discovered.items()):
        state = "enabled" if name in enabled_set else "available"
        source = entry.value if hasattr(entry, "value") else entry.__module__  # type: ignore[union-attr]
        typer.echo(f"  {name:<30} [{state}]  ({source})")


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
    if plugin.settings_class:
        typer.echo(f"Settings:    {plugin.settings_class.__name__}")
        for field_name, field_info in plugin.settings_class.model_fields.items():
            default = field_info.default
            annotation = field_info.annotation
            type_name = getattr(annotation, "__name__", str(annotation))
            typer.echo(f"  {field_name}: {type_name} = {default!r}")
    if plugin.system_deps:
        typer.echo(f"System deps: {', '.join(plugin.system_deps)}")


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
