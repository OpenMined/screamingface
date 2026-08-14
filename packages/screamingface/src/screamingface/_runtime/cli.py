from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from screamingface._runtime.config import RuntimeConfig, default_data_dir

_PORTS = (9105, 9106, 9108)
_HEALTH = {
    "gateway": "http://127.0.0.1:9105/healthz",
    "scoreboard": "http://127.0.0.1:9106/healthz",
    "engine": "http://127.0.0.1:9108/healthz",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="screamingface")
    parser.add_argument(
        "--version", action="version", version=importlib.metadata.version("screamingface")
    )
    _add_data_dir(parser, default=default_data_dir())
    commands = parser.add_subparsers(dest="command", required=True)
    up = commands.add_parser("up", help="Start the local runtime")
    _add_data_dir(up)
    up.add_argument("--foreground", action="store_true")
    down = commands.add_parser("down", help="Stop the local runtime")
    _add_data_dir(down)
    status = commands.add_parser("status", help="Show local runtime status")
    _add_data_dir(status)
    logs = commands.add_parser("logs", help="Read local runtime logs")
    _add_data_dir(logs)
    logs.add_argument("--tail", type=int, default=100)
    logs.add_argument("--no-follow", action="store_true")
    prepare = commands.add_parser("prepare", help="Download benchmark assets")
    _add_data_dir(prepare)
    prepare.add_argument("benchmark", nargs="?", choices=("draco", "ifeval", "healthbench"))
    prepare.add_argument("--all", action="store_true", dest="all_benchmarks")
    serve = commands.add_parser("_serve", help=argparse.SUPPRESS)
    _add_data_dir(serve)
    serve.add_argument("--owner-token", required=True)
    scoreboard = commands.add_parser("_scoreboard", help=argparse.SUPPRESS)
    _add_data_dir(scoreboard)
    commands._choices_actions = [  # noqa: SLF001
        action
        for action in commands._choices_actions  # noqa: SLF001
        if action.dest not in {"_serve", "_scoreboard"}
    ]
    return parser


def _add_data_dir(parser: argparse.ArgumentParser, *, default: Path | None = None) -> None:
    if default is None:
        parser.add_argument("--data-dir", type=Path, default=argparse.SUPPRESS)
    else:
        parser.add_argument("--data-dir", type=Path, default=default)


def main(argv: list[str] | None = None) -> None:  # noqa: C901, PLR0912
    args = _parser().parse_args(argv)
    config = RuntimeConfig(data_dir=args.data_dir)
    try:
        if args.command == "up":
            _up(config, foreground=args.foreground)
        elif args.command == "down":
            _down(config)
        elif args.command == "status":
            raise SystemExit(_print_status(config))
        elif args.command == "logs":
            _logs(config, tail=args.tail, follow=not args.no_follow)
        elif args.command == "prepare":
            _prepare(config, args.benchmark, all_benchmarks=args.all_benchmarks)
        elif args.command == "_serve":
            _serve(config, args.owner_token)
        elif args.command == "_scoreboard":
            from screamingface._runtime.server import run_scoreboard

            run_scoreboard(config)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"screamingface: {exc}") from None


def _up(config: RuntimeConfig, *, foreground: bool) -> None:  # noqa: PLR0915
    from screamingface._runtime.server import require_runtime_extra

    require_runtime_extra()
    state = _read_state(config)
    health = _health()
    if state and _pid_alive(state.get("pid")) and all(health.values()):
        print("ScreamingFace is already running.")
        _print_urls(config)
        return
    occupied = [port for port in _PORTS if _port_open(port)]
    if occupied:
        raise RuntimeError(f"required port(s) already in use by another process: {occupied}")
    config.data_dir.mkdir(parents=True, exist_ok=True)
    token = os.urandom(16).hex()
    if foreground:
        _write_state(config, os.getpid(), token)
        try:
            _run_server(config)
        finally:
            _remove_owned_state(config, token)
        return

    log = config.log_path.open("a", encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "screamingface._runtime.cli",
        "--data-dir",
        str(config.data_dir),
        "_serve",
        "--owner-token",
        token,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    _write_state(config, process.pid, token)
    try:
        _wait_ready(process, timeout=90)
    except Exception:
        if process.poll() is None:
            process.terminate()
        _remove_owned_state(config, token)
        raise
    print("ScreamingFace is ready.")
    _print_urls(config)


def _serve(config: RuntimeConfig, token: str) -> None:
    state = _read_state(config)
    if not state or state.get("owner_token") != token or state.get("pid") != os.getpid():
        raise RuntimeError("runtime ownership state does not match this process")
    try:
        _run_server(config)
    finally:
        _remove_owned_state(config, token)


def _run_server(config: RuntimeConfig) -> None:
    import asyncio

    from screamingface._runtime.server import run

    asyncio.run(run(config))


def _down(config: RuntimeConfig) -> None:
    state = _read_state(config)
    if not state:
        print("ScreamingFace is not running.")
        return
    pid = state.get("pid")
    token = state.get("owner_token")
    if not isinstance(pid, int) or not isinstance(token, str):
        raise RuntimeError(f"invalid runtime state: {config.state_path}")
    if not _pid_alive(pid):
        _remove_owned_state(config, token)
        print("Removed stale runtime state; ScreamingFace was not running.")
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not _pid_alive(pid):
            _remove_owned_state(config, token)
            print("ScreamingFace stopped.")
            return
        time.sleep(0.1)
    raise RuntimeError(f"runtime process {pid} did not stop; inspect {config.log_path}")


def _print_status(config: RuntimeConfig) -> int:
    state = _read_state(config)
    health = _health()
    alive = bool(state and _pid_alive(state.get("pid")))
    if alive and all(health.values()):
        label, code = "running", 0
    elif alive:
        label, code = "partially healthy", 1
    elif any(health.values()) or any(_port_open(port) for port in _PORTS):
        label, code = "foreign processes occupy runtime ports", 2
    else:
        label, code = "stopped", 1
    print(f"ScreamingFace: {label}")
    for name, ready in health.items():
        base_url = _HEALTH[name].removesuffix("/healthz")
        print(f"  {name:10} {'UP' if ready else 'down':4}  {base_url}")
    print(f"  logs       {config.log_path}")
    return code


def _logs(config: RuntimeConfig, *, tail: int, follow: bool) -> None:
    if tail < 0:
        raise RuntimeError("--tail must be zero or greater")
    if not config.log_path.exists():
        raise RuntimeError(f"no runtime log exists at {config.log_path}")
    with config.log_path.open(encoding="utf-8", errors="replace") as stream:
        for line in deque(stream, maxlen=tail):
            print(line, end="")
        if not follow:
            return
        while True:
            line = stream.readline()
            if line:
                print(line, end="", flush=True)
            else:
                time.sleep(0.2)


def _prepare(config: RuntimeConfig, benchmark: str | None, *, all_benchmarks: bool) -> None:
    from screamingface._runtime.server import require_runtime_extra

    require_runtime_extra()
    if all_benchmarks == (benchmark is not None):
        raise RuntimeError("choose one benchmark or pass --all")
    selected = ("draco", "ifeval", "healthbench") if all_benchmarks else (benchmark,)
    config.assets_dir.mkdir(parents=True, exist_ok=True)
    for name in selected:
        destination = config.assets_dir / str(name)
        subprocess.run(
            [
                sys.executable,
                "-m",
                f"screamingface_engine.benchmarks.{name}.prepare",
                "--out",
                str(destination),
            ],
            check=True,
        )
    print(f"Benchmark assets ready at {config.assets_dir}")


def _wait_ready(process: subprocess.Popen[bytes], *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("runtime exited during startup; inspect the runtime log")
        if all(_health().values()):
            return
        time.sleep(0.2)
    raise RuntimeError("runtime did not become ready within 90 seconds")


def _health() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for name, url in _HEALTH.items():
        try:
            with urlopen(url, timeout=0.3) as response:  # noqa: S310
                result[name] = response.status == 200
        except (OSError, URLError):
            result[name] = False
    return result


def _port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    except PermissionError:
        alive = True
    except OSError:
        alive = False
    else:
        alive = True
    return alive


def _read_state(config: RuntimeConfig) -> dict[str, object] | None:
    try:
        value = json.loads(config.state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(config: RuntimeConfig, pid: int, token: str) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    temporary = config.state_path.with_name(f".{config.state_path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": pid, "owner_token": token}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config.state_path)
        config.state_path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_owned_state(config: RuntimeConfig, token: str) -> None:
    state = _read_state(config)
    if state and state.get("owner_token") == token:
        config.state_path.unlink(missing_ok=True)


def _print_urls(config: RuntimeConfig) -> None:
    for name, url in (("Gateway", 9105), ("Scoreboard", 9106), ("Engine", 9108)):
        print(f"  {name:10} http://127.0.0.1:{url}")
    print(f"  Logs       {config.log_path}")


if __name__ == "__main__":
    main()
