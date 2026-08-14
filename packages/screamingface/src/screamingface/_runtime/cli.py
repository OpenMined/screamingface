from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from screamingface._runtime.config import RuntimeConfig, default_data_dir

_STATE_VERSION = 1
_PORT_DEFAULTS = {"gateway": 9105, "scoreboard": 9106, "engine": 9108}
_BENCHMARKS = ("draco", "ifeval", "healthbench")


def _parser() -> argparse.ArgumentParser:  # noqa: PLR0915
    parser = argparse.ArgumentParser(prog="screamingface")
    parser.add_argument(
        "--version", action="version", version=importlib.metadata.version("screamingface")
    )
    _add_data_dir(parser, default=default_data_dir())
    commands = parser.add_subparsers(dest="command", required=True)
    up = commands.add_parser("up", help="Start the local runtime")
    _add_data_dir(up)
    up.add_argument("--foreground", action="store_true")
    _add_port_options(up)
    down = commands.add_parser("down", help="Stop the local runtime")
    _add_data_dir(down)
    restart = commands.add_parser("restart", help="Restart the local runtime")
    _add_data_dir(restart)
    restart.add_argument("--foreground", action="store_true")
    _add_port_options(restart)
    status = commands.add_parser("status", help="Show local runtime status")
    _add_data_dir(status)
    status.add_argument("--json", action="store_true", dest="json_output")
    logs = commands.add_parser("logs", help="Read local runtime logs")
    _add_data_dir(logs)
    logs.add_argument("--tail", type=int, default=100)
    logs.add_argument("--no-follow", action="store_true")
    prepare = commands.add_parser("prepare", help="Download benchmark assets")
    _add_data_dir(prepare)
    prepare.add_argument("benchmark", nargs="?", choices=_BENCHMARKS)
    prepare.add_argument("--all", action="store_true", dest="all_benchmarks")
    serve = commands.add_parser("_serve", help=argparse.SUPPRESS)
    _add_data_dir(serve)
    serve.add_argument("--owner-token", required=True)
    _add_port_options(serve)
    scoreboard = commands.add_parser("_scoreboard", help=argparse.SUPPRESS)
    _add_data_dir(scoreboard)
    scoreboard.add_argument("--scoreboard-port", type=int, default=9106)
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


def _add_port_options(parser: argparse.ArgumentParser) -> None:
    for service in _PORT_DEFAULTS:
        parser.add_argument(f"--{service}-port", type=int, default=None)


def main(argv: list[str] | None = None) -> None:  # noqa: C901, PLR0912
    args = _parser().parse_args(argv)
    try:
        config = _config(args)
        if args.command == "up":
            _up(config, foreground=args.foreground)
        elif args.command == "restart":
            _restart(config, args, foreground=args.foreground)
        elif args.command == "down":
            _down(config)
        elif args.command == "status":
            raise SystemExit(_print_status(config, json_output=args.json_output))
        elif args.command == "logs":
            _logs(config, tail=args.tail, follow=not args.no_follow)
        elif args.command == "prepare":
            _prepare(config, args.benchmark, all_benchmarks=args.all_benchmarks)
        elif args.command == "_serve":
            _serve(config, args.owner_token)
        elif args.command == "_scoreboard":
            from screamingface._runtime.server import run_scoreboard

            run_scoreboard(config)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        raise SystemExit(f"screamingface: {exc}") from None


def _config(args: argparse.Namespace) -> RuntimeConfig:
    values: dict[str, int] = {}
    for service, fallback in _PORT_DEFAULTS.items():
        argument = getattr(args, f"{service}_port", None)
        configured = os.getenv(f"SCREAMINGFACE_{service.upper()}_PORT")
        values[service] = (
            argument if argument is not None else _environment_port(configured, fallback)
        )
    return RuntimeConfig(
        data_dir=args.data_dir,
        gateway_port=values["gateway"],
        scoreboard_port=values["scoreboard"],
        engine_port=values["engine"],
    )


def _environment_port(value: str | None, fallback: int) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"runtime port must be an integer, got {value!r}") from None


def _up(config: RuntimeConfig, *, foreground: bool) -> None:  # noqa: PLR0915
    from screamingface._runtime.server import require_runtime_extra

    require_runtime_extra()
    state = _read_state(config)
    owned = bool(state and _verify_owner(state))
    if owned:
        health = _health(_state_services(state))
        if all(health.values()):
            print("ScreamingFace is already running.")
            _print_urls(_state_services(state), config.log_path)
            return
        raise RuntimeError(
            "the owned runtime is only partially healthy; run `screamingface logs` "
            "then `screamingface restart`"
        )
    if state:
        config.state_path.unlink(missing_ok=True)
    occupied = [port for port in _ports(config) if _port_open(port)]
    if occupied:
        raise RuntimeError(f"required port(s) already in use by another process: {occupied}")
    config.data_dir.mkdir(parents=True, exist_ok=True)
    token = os.urandom(16).hex()
    if foreground:
        _serve(config, token)
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
        "--gateway-port",
        str(config.gateway_port),
        "--scoreboard-port",
        str(config.scoreboard_port),
        "--engine-port",
        str(config.engine_port),
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
    try:
        _wait_ready(process, config, timeout=90)
    except Exception:
        state = _read_state(config)
        if state and _verify_owner(state):
            _request_shutdown(state)
        raise
    print("ScreamingFace is ready.")
    _print_urls(config.services, config.log_path)


def _serve(config: RuntimeConfig, token: str) -> None:
    shutdown = threading.Event()
    control = _control_server(token, shutdown)
    started_at = datetime.now(UTC).isoformat()
    state = {
        "schema_version": _STATE_VERSION,
        "pid": os.getpid(),
        "process_started_at": time.time(),
        "started_at": started_at,
        "owner_token": token,
        "control_url": f"http://127.0.0.1:{control.server_port}",
        "services": config.services,
        "log_path": str(config.log_path),
    }
    _write_state(config, state)
    control_thread = threading.Thread(target=control.serve_forever, daemon=True)
    control_thread.start()
    try:
        _run_server(config, shutdown)
    finally:
        control.shutdown()
        control.server_close()
        control_thread.join(timeout=2)
        _remove_owned_state(config, token)


def _run_server(config: RuntimeConfig, shutdown: threading.Event) -> None:
    import asyncio

    from screamingface._runtime.server import run

    asyncio.run(run(config, shutdown))


def _down(config: RuntimeConfig) -> None:
    state = _read_state(config)
    if not state:
        print("ScreamingFace is not running.")
        return
    if not _verify_owner(state):
        config.state_path.unlink(missing_ok=True)
        print("Removed stale runtime state; no owned ScreamingFace runtime was stopped.")
        return
    _request_shutdown(state)
    for _ in range(100):
        if not _verify_owner(state):
            config.state_path.unlink(missing_ok=True)
            print("ScreamingFace stopped.")
            return
        time.sleep(0.1)
    raise RuntimeError(f"runtime did not stop; inspect {config.log_path}")


def _restart(config: RuntimeConfig, args: argparse.Namespace, *, foreground: bool) -> None:
    state = _read_state(config)
    if state:
        services = _state_services(state)
        stored = {name: _url_port(url) for name, url in services.items()}
        values = {}
        for service, fallback in _PORT_DEFAULTS.items():
            explicit = getattr(args, f"{service}_port", None)
            environment = os.getenv(f"SCREAMINGFACE_{service.upper()}_PORT")
            values[service] = (
                explicit
                if explicit is not None
                else _environment_port(environment, stored.get(service, fallback))
            )
        config = RuntimeConfig(
            data_dir=config.data_dir,
            gateway_port=values["gateway"],
            scoreboard_port=values["scoreboard"],
            engine_port=values["engine"],
        )
    _down(config)
    _up(config, foreground=foreground)


def _print_status(config: RuntimeConfig, *, json_output: bool = False) -> int:
    state = _read_state(config)
    services = _state_services(state) if state else config.services
    health = _health(services)
    owned = bool(state and _verify_owner(state))
    if owned and all(health.values()):
        label, code = "running", 0
    elif owned:
        label, code = "partially healthy", 1
    elif any(health.values()) or any(_port_open(port) for port in _service_ports(services)):
        label, code = "foreign processes occupy runtime ports", 2
    else:
        label, code = "stopped", 1
    if json_output:
        payload = {
            "schema": "screamingface.runtime-status.v1",
            "status": label.replace(" ", "_"),
            "ownership_verified": owned,
            "pid": state.get("pid") if state else None,
            "started_at": state.get("started_at") if state else None,
            "data_dir": str(config.data_dir),
            "services": {
                name: {"url": url, "healthy": health[name]} for name, url in services.items()
            },
            "log_path": str(config.log_path),
            "benchmarks": _benchmark_statuses(config),
        }
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return code
    print(f"ScreamingFace: {label}")
    for name, ready in health.items():
        print(f"  {name:10} {'UP' if ready else 'down':4}  {services[name]}")
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
    selected = _BENCHMARKS if all_benchmarks else (benchmark,)
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


def _benchmark_statuses(config: RuntimeConfig) -> dict[str, str]:
    return {
        name: ("incomplete" if (config.assets_dir / name).exists() else "missing")
        for name in _BENCHMARKS
    }


def _wait_ready(process: subprocess.Popen[bytes], config: RuntimeConfig, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("runtime exited during startup; inspect the runtime log")
        state = _read_state(config)
        if all(_health(config.services).values()) and state is not None and _verify_owner(state):
            return
        time.sleep(0.2)
    raise RuntimeError("runtime did not become ready within 90 seconds")


def _health(services: dict[str, str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for name, base_url in services.items():
        url = f"{base_url}/healthz"
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


def _write_state(config: RuntimeConfig, state: dict[str, object]) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    temporary = config.state_path.with_name(f".{config.state_path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(state, sort_keys=True) + "\n")
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


def _print_urls(services: dict[str, str], log_path: Path) -> None:
    for name, url in services.items():
        print(f"  {name.title():10} {url}")
    print(f"  Logs       {log_path}")
    print(f"  export SCREAMINGFACE_ENGINE_URL={services['engine']}")
    print(f"  export SCREAMINGFACE_SCOREBOARD_URL={services['scoreboard']}")


def _ports(config: RuntimeConfig) -> tuple[int, int, int]:
    return config.gateway_port, config.scoreboard_port, config.engine_port


def _service_ports(services: dict[str, str]) -> tuple[int, ...]:
    return tuple(_url_port(url) for url in services.values())


def _url_port(url: str) -> int:
    from urllib.parse import urlsplit

    port = urlsplit(url).port
    if port is None:
        raise ValueError(f"runtime service URL has no port: {url}")
    return port


def _state_services(state: dict[str, object] | None) -> dict[str, str]:
    if not state or state.get("schema_version") != _STATE_VERSION:
        return {}
    value = state.get("services")
    if not isinstance(value, dict):
        return {}
    services = {str(name): str(url) for name, url in value.items()}
    return services if set(services) == set(_PORT_DEFAULTS) else {}


def _verify_owner(state: dict[str, object]) -> bool:
    control_url = state.get("control_url")
    token = state.get("owner_token")
    pid = state.get("pid")
    if not isinstance(control_url, str) or not isinstance(token, str) or not isinstance(pid, int):
        return False
    try:
        request = Request(f"{control_url}/identity", headers={"Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=0.5) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, URLError, ValueError):
        return False
    return isinstance(payload, dict) and payload == {
        "pid": pid,
        "owner_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }


def _request_shutdown(state: dict[str, object]) -> None:
    control_url = state["control_url"]
    token = state["owner_token"]
    request = Request(
        f"{control_url}/shutdown",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=2):  # noqa: S310
            return
    except (OSError, URLError) as exc:
        raise RuntimeError("owned runtime rejected the shutdown request") from exc


def _control_server(token: str, shutdown: threading.Event) -> ThreadingHTTPServer:
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/identity" or not self._authorized():
                self.send_error(404)
                return
            self._json({"pid": os.getpid(), "owner_token_sha256": token_hash})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/shutdown" or not self._authorized():
                self.send_error(404)
                return
            self._json({"status": "stopping"})
            shutdown.set()

        def _authorized(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _json(self, value: dict[str, Any]) -> None:
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


if __name__ == "__main__":
    main()
