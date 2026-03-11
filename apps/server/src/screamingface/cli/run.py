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
    ssl: Annotated[
        bool | None,
        typer.Option("--ssl/--no-ssl", help="Enable SSL (default: from config)"),
    ] = None,
    ssl_certfile: Annotated[
        str | None,
        typer.Option("--ssl-certfile", help="Path to SSL certificate file"),
    ] = None,
    ssl_keyfile: Annotated[
        str | None,
        typer.Option("--ssl-keyfile", help="Path to SSL key file"),
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
    if ssl is not None:
        cfg.server.ssl = ssl
    if ssl_certfile is not None:
        cfg.server.ssl_certfile = ssl_certfile
    if ssl_keyfile is not None:
        cfg.server.ssl_keyfile = ssl_keyfile

    # Plugin filtering
    if enable is not None:
        cfg.plugins = enable
    elif disable is not None:
        cfg.plugins = [p for p in cfg.plugins if p not in disable]

    # SSL setup
    ssl_certfile_path: str | None = None
    ssl_keyfile_path: str | None = None
    if cfg.server.ssl:
        certfile = cfg.server.ssl_certfile
        keyfile = cfg.server.ssl_keyfile
        if certfile and keyfile:
            # Use user-provided paths (expand ~)
            ssl_certfile_path = str(Path(certfile).expanduser())
            ssl_keyfile_path = str(Path(keyfile).expanduser())
        else:
            # Auto-generate certs with mkcert
            from screamingface.core.ssl import ensure_ssl

            cert, key = ensure_ssl()
            ssl_certfile_path = str(cert)
            ssl_keyfile_path = str(key)

    uvicorn.run(
        "screamingface.core.app:create_app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=cfg.server.reload,
        factory=True,
        ssl_certfile=ssl_certfile_path,
        ssl_keyfile=ssl_keyfile_path,
    )
