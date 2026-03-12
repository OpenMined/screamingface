"""CLI commands for the claude-env plugin: sf claude-env status/off."""

from __future__ import annotations

import typer

from screamingface.plugins.claude_env.shellenv import (
    current_exports,
    has_exports,
    remove_exports,
    shell_profiles,
)

claude_env_app = typer.Typer(
    name="claude-env",
    help="Manage Claude Code environment variable redirection.",
    no_args_is_help=True,
)


@claude_env_app.command()
def status() -> None:
    """Show current claude-env state."""
    if has_exports():
        exports = current_exports()
        typer.echo("Claude Env: ACTIVE")
        for profile in shell_profiles():
            typer.echo(f"  Profile: {profile}")
        for key, value in exports.items():
            typer.echo(f"  {key}={value}")
    else:
        typer.echo("Claude Env: INACTIVE")
        typer.echo("  No exports in shell profiles")


@claude_env_app.command()
def off() -> None:
    """Remove Claude Code env vars from shell profiles."""
    remove_exports()
    for profile in shell_profiles():
        typer.echo(f"Removed exports from {profile}")
    typer.echo("Open a new terminal for changes to take effect.")
