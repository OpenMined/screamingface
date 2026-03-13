"""CLI commands for the claude-intercept plugin: sf claude-intercept status/off."""

from __future__ import annotations

import typer

from screamingface.plugins.claude_intercept.hosts import flush_dns, has_entries, remove_entries
from screamingface.plugins.claude_intercept.plugin import ClaudeInterceptPlugin
from screamingface.plugins.claude_intercept.state import clear_state, is_stale, load_state
from screamingface.plugins.claude_intercept.trust import remove_node_ca_trust

claude_intercept_app = typer.Typer(
    name="claude-intercept",
    help="Manage DNS/SSL interception for AI API traffic.",
    no_args_is_help=True,
)


@claude_intercept_app.command()
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
            typer.echo(
                "  WARNING: /etc/hosts still has intercept entries (run 'sf claude-intercept off')"
            )


@claude_intercept_app.command()
def off() -> None:
    """Force cleanup — remove DNS entries and port forwarding."""
    typer.echo("Cleaning up intercept state...")
    remove_entries()
    flush_dns()
    ClaudeInterceptPlugin._teardown_port_forward()
    remove_node_ca_trust()
    clear_state()
    typer.echo("Done. DNS, port forwarding, and shell profiles restored.")
