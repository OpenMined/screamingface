"""CLI commands for the intercept plugin: sf intercept status/off."""

from __future__ import annotations

import typer

from screamingface.plugins.intercept.hosts import flush_dns, has_entries, remove_entries
from screamingface.plugins.intercept.plugin import InterceptPlugin
from screamingface.plugins.intercept.state import clear_state, is_stale, load_state

intercept_app = typer.Typer(
    name="intercept",
    help="Manage DNS/SSL interception for AI API traffic.",
    no_args_is_help=True,
)


@intercept_app.command()
def status() -> None:
    """Show current intercept state."""
    state = load_state()
    hosts_active = has_entries()

    if state and state.active:
        stale = is_stale()
        label = " (STALE — server PID dead)" if stale else ""
        typer.echo(f"Intercept: ACTIVE{label}")
        typer.echo(f"  PID: {state.pid}")
        typer.echo(f"  Domains: {', '.join(state.domains)}")
        typer.echo(f"  Since: {state.activated_at}")
        typer.echo(f"  /etc/hosts modified: {hosts_active}")
    else:
        typer.echo("Intercept: INACTIVE")
        if hosts_active:
            typer.echo("  WARNING: /etc/hosts still has intercept entries (run 'sf intercept off')")


@intercept_app.command()
def off() -> None:
    """Force cleanup — remove DNS entries and port forwarding."""
    typer.echo("Cleaning up intercept state...")
    remove_entries()
    flush_dns()
    InterceptPlugin._teardown_port_forward()
    clear_state()
    typer.echo("Done. DNS and port forwarding restored.")
