"""Typer root CLI app — the `sf` command."""

import typer

from screamingface.cli.plugin import plugin_app
from screamingface.cli.run import run

app = typer.Typer(
    name="sf",
    help="ScreamingFace — plugin-based AI ensemble server.",
    no_args_is_help=True,
)

app.command()(run)
app.add_typer(plugin_app, name="plugin")
