from __future__ import annotations

import argparse
import subprocess
import sys

import uvicorn

from .config import Settings

# WHY: one public migration entry point for Helm, local development, and plain Docker. The raw
# Tortoise invocation lives here alone, so deployment launchers cannot drift from application
# migration configuration.
_MIGRATE_COMMAND = [
    sys.executable,
    "-m",
    "tortoise",
    "-c",
    "aigateway.db.TORTOISE_CONFIG",
    "migrate",
]


def _serve() -> None:
    settings = Settings()
    uvicorn.run(
        "aigateway.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


def _migrate() -> None:
    result = subprocess.run(_MIGRATE_COMMAND, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aigateway")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the HTTP server (default).")
    subparsers.add_parser("migrate", help="Apply pending Tortoise migrations, then exit.")
    args = parser.parse_args(argv)

    if args.command == "migrate":
        _migrate()
    else:
        _serve()


if __name__ == "__main__":
    main()
