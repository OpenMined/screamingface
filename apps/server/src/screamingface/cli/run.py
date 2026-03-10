"""The `sf run` command — start the server."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


def run(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file (default: sf.json)"),
    ] = None,
    host: Annotated[
        str | None,
        typer.Option("--host", help="Bind host (overrides config)"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Bind port (overrides config)"),
    ] = None,
    enable: Annotated[
        list[str] | None,
        typer.Option("--enable", help="Only enable these plugins (repeatable)"),
    ] = None,
    disable: Annotated[
        list[str] | None,
        typer.Option("--disable", help="Disable these plugins from config (repeatable)"),
    ] = None,
    reload: Annotated[
        bool | None,
        typer.Option("--reload/--no-reload", help="Enable auto-reload"),
    ] = None,
) -> None:
    """Start the ScreamingFace server."""
    import uvicorn

    from screamingface.core.config import load_config

    cfg = load_config(config)

    # Apply CLI overrides
    if host is not None:
        cfg.server.host = host
    if port is not None:
        cfg.server.port = port
    if reload is not None:
        cfg.server.reload = reload

    # Plugin filtering
    if enable is not None:
        cfg.plugins = enable
    elif disable is not None:
        cfg.plugins = [p for p in cfg.plugins if p not in disable]

    uvicorn.run(
        "screamingface.core.app:create_app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=cfg.server.reload,
        factory=True,
    )
