"""Command-line entry point for the url4 node server (``url4`` console script).

``url4 serve`` stands up the engine as an HTTP node (assembly in :mod:`url4._serve`);
``url4 eval`` evaluates one expression network-free. This module is kept free of any
web framework at import time so ``url4 --version`` and ``url4 eval`` work on the base
install — uvicorn (the ``url4[server]`` extra) is imported only when serving, and the
serve assembly (:mod:`url4._serve`) is imported lazily inside :func:`_run_serve`.

# STORY: as an operator, I run `url4 serve` to expose the url4 engine over HTTP with my
# model routes, and `url4 eval '<expr>'` to sanity-check an expression with no backend.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from url4 import __version__
from url4.errors import Url4Error

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", ""})

_SERVE_FIELDS = (
    "host",
    "port",
    "backend_url",
    "backend_token",
    "processor",
    "eval_path",
    "concurrency",
    "max_inflight",
    "timeout",
    "routes",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and dispatch. Returns the process exit code (0/1/2)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "eval":
        return _run_eval(args)
    return _run_serve(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="url4", description="Run or query a url4 node.")
    parser.add_argument("--version", action="version", version=f"url4 {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_serve_parser(sub)
    _add_eval_parser(sub)
    return parser


def _add_serve_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("serve", help="run the node as an HTTP server (foreground)")
    parser.add_argument("--host", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (default 4404)")
    parser.add_argument("--backend-url", dest="backend_url", help="aigateway base URL")
    parser.add_argument(
        "--backend-token",
        dest="backend_token",
        help="path to a token file, or '-' to read one line from stdin (never the raw token)",
    )
    parser.add_argument("--processor", help="reduce route (default /claude); must be a route")
    parser.add_argument("--eval-path", dest="eval_path", help="eval endpoint path (default /v1)")
    parser.add_argument("--concurrency", type=int, help="run-wide I/O cap (default 32)")
    parser.add_argument(
        "--max-inflight", dest="max_inflight", type=int, help="max concurrent evals (default 16)"
    )
    parser.add_argument("--timeout", type=float, help="per-request timeout seconds (default 120)")
    parser.add_argument("--config", help="url4.toml path (default ./url4.toml if present)")
    parser.add_argument(
        "--route", dest="routes", action="append", metavar="PATH=MODEL", help="add/override a route"
    )


def _add_eval_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("eval", help="evaluate one expression network-free (no backend)")
    parser.add_argument("expression", nargs="?", help="url4 expression; omit to read from stdin")


# --- eval ------------------------------------------------------------------------


def _run_eval(args: argparse.Namespace) -> int:
    expression = (args.expression if args.expression is not None else sys.stdin.read()).strip()
    if not expression:
        print("url4 eval: no expression (pass an argument or pipe one on stdin)", file=sys.stderr)
        return 2
    from url4 import StaticIOLayer, evaluate_sync

    try:
        result = evaluate_sync(expression, StaticIOLayer())
    except Url4Error as exc:
        print(f"url4 eval: {exc}", file=sys.stderr)
        return 1
    print(result.text)
    return 0


# --- serve -----------------------------------------------------------------------


def _run_serve(args: argparse.Namespace) -> int:
    from url4 import _serve  # lazy: keeps httpx/subprocess assembly off the base import path

    try:
        config = _serve.resolve(_overrides(args), os.environ, _config_path(args))
        config.validate()
    except _serve.ConfigError as exc:
        print(f"url4 serve: {exc}", file=sys.stderr)
        return 2
    _warn_exposure(config)
    client = _serve.build_client(config)
    node = _serve.build_node(config, client)
    app = _serve.build_asgi_app(node, client, config)
    print(
        f"url4 serve: listening on http://{config.host}:{config.port} "
        f"(eval {config.eval_path}?q=…)",
        file=sys.stderr,
    )
    return _serve_forever(app, config.host, config.port)


def _overrides(args: argparse.Namespace) -> dict[str, object]:
    return {name: getattr(args, name) for name in _SERVE_FIELDS}


def _config_path(args: argparse.Namespace) -> Path | None:
    explicit = args.config or os.environ.get("URL4_CONFIG")
    if explicit:
        return Path(explicit)
    default = Path("url4.toml")
    return default if default.is_file() else None


def _warn_exposure(config) -> None:
    if config.host in _LOOPBACK:
        return
    print(
        f"url4 serve: WARNING binding non-loopback host {config.host!r} — the eval endpoint "
        "evaluates arbitrary url4 and fetches arbitrary URLs.",
        file=sys.stderr,
    )
    if config.commands:
        print(
            "url4 serve: WARNING command routes are enabled and now remotely reachable — "
            f"they run local subprocesses: {sorted(config.commands)}",
            file=sys.stderr,
        )


def _serve_forever(app, host: str, port: int) -> int:
    # WHY: importlib (not a static `import uvicorn`) so the optional extra stays
    # truly optional — the type checker doesn't demand it and the missing-extra
    # branch is exercisable in an env without it (mirrors Url4Node.serve).
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ModuleNotFoundError:
        print(
            "url4 serve: uvicorn is required — install with: pip install 'url4[server]'",
            file=sys.stderr,
        )
        return 2
    uvicorn.run(app, host=host, port=port)  # pragma: no cover - needs the extra + a real bind
    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
