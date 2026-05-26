"""Typer sub-app for the plugin-audit plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

plugin_audit_app = typer.Typer(
    help="Audit plugin dependency declarations.",
    no_args_is_help=True,
)


@plugin_audit_app.command("deps")
def audit_deps(
    plugins_root: Annotated[
        Path,
        typer.Option(
            "--plugins-root",
            help="Directory containing plugin subdirectories.",
        ),
    ] = Path("src/screamingface/plugins"),
    report: Annotated[
        Path,
        typer.Option(
            "--report",
            help="Path to write the markdown audit report.",
        ),
    ] = Path("../../docs/superpowers/plans/plugin-dependency-audit.md"),
) -> None:
    """Audit cross-plugin imports vs declared Plugin.depends manifests."""
    from screamingface.plugins.plugin_audit.audit import (
        audit_all,
        find_cycles,
        render_report,
    )

    findings = audit_all(plugins_root)
    cycles = find_cycles(findings)
    report.write_text(render_report(findings, cycles, plugins_root))
    typer.echo(f"wrote {report}")
