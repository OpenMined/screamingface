"""The `sf run` command — start the server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer


def run(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file (default: sf.json)"),
    ] = None,
    config_json: Annotated[
        str | None,
        typer.Option("--config-json", help="Inline JSON config (alternative to --config file)"),
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
    subprocess_mode: Annotated[
        bool,
        typer.Option("--subprocess", help="Subprocess mode (structured ready event, no reload)"),
    ] = False,
) -> None:
    """Start the ScreamingFace server."""
    import uvicorn

    from screamingface.core.config import CONFIG_ENV_VAR, AppConfig, load_config

    # Config resolution: --config-json > --config file > SF_CONFIG env > sf.json
    if config_json is not None:
        cfg = AppConfig.model_validate_json(config_json)
    elif config is not None:
        cfg = load_config(config)
    else:
        raw_env = os.environ.get(CONFIG_ENV_VAR, "")
        if raw_env:
            cfg = AppConfig.model_validate_json(raw_env)
        else:
            cfg = load_config()

    # Subprocess mode: force no-reload, signal via env var
    if subprocess_mode:
        cfg.server.reload = False
        os.environ["_SF_SUBPROCESS"] = "1"

    # Check if any enabled plugin requires a specific port
    required_port_by_plugin: int | None = None
    if cfg.plugins:
        from screamingface.core.registry import PluginRegistry

        _reg = PluginRegistry()
        _reg.discover()
        for pname in cfg.plugins:
            if pname in _reg.discovered_plugins:
                p = _reg.load_plugin(pname)
                if p.required_port is not None:
                    required_port_by_plugin = p.required_port
                    break

    if required_port_by_plugin is not None:
        # Plugin demands a specific port — force it, skip auto-increment
        cfg.server.port = required_port_by_plugin
    elif port is None:
        # Auto-pick a free port if the configured one is busy (increment +1, +2, …)
        import socket

        candidate = cfg.server.port
        while candidate < cfg.server.port + 100:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", candidate)) != 0:
                    break
            candidate += 1
        cfg.server.port = candidate

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
        elif "claude-intercept" in cfg.plugins:
            # Claude-intercept plugin needs certs that cover intercepted domains.
            # Generate them here since uvicorn.run() needs paths before
            # the plugin's setup() runs inside the factory.
            from screamingface.plugins.claude_intercept.certs import ensure_intercept_certs

            intercept_cfg = cfg.plugin_config.get("claude-intercept", {})
            domains = intercept_cfg.get("domains", ["api.anthropic.com"])
            cert, key = ensure_intercept_certs(domains)  # type: ignore[arg-type]
            ssl_certfile_path = str(cert)
            ssl_keyfile_path = str(key)
        else:
            # Auto-generate certs with mkcert
            from screamingface.core.ssl import ensure_ssl

            cert, key = ensure_ssl()
            ssl_certfile_path = str(cert)
            ssl_keyfile_path = str(key)

    # Serialize resolved config to env var so it survives uvicorn's
    # reloader fork (module-level state doesn't persist across forks).
    os.environ["_SF_RUNTIME_CONFIG"] = cfg.model_dump_json()

    uvicorn.run(
        "screamingface.core.app:create_app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=cfg.server.reload,
        factory=True,
        log_level="info",
        ssl_certfile=ssl_certfile_path,
        ssl_keyfile=ssl_keyfile_path,
    )
