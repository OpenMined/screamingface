from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping
from types import FrameType
from typing import Any, Protocol

from screamingface._runtime.config import RuntimeConfig, scoreboard_assets

SERVICES = {
    "gateway": "http://127.0.0.1:9105",
    "scoreboard": "http://127.0.0.1:9106",
    "engine": "http://127.0.0.1:9108",
}
STARTUP_TIMEOUT_SECONDS = 90.0


class Server(Protocol):
    started: bool
    should_exit: bool

    async def serve(self) -> None: ...


def require_runtime_extra() -> None:
    try:
        import aigateway  # noqa: F401
        import scoreboard  # noqa: F401
        import url4_cloud  # noqa: F401
        import uvicorn  # pyright: ignore[reportMissingImports]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            'Local runtime dependencies are missing. Install "screamingface[runtime]".'
        ) from exc


async def run(config: RuntimeConfig) -> None:
    require_runtime_extra()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    await _migrate(config)
    gateway, engine = _build_apps(config)
    servers = (
        _server(gateway, 9105, "AI Gateway"),
        _server(engine, 9108, "Engine"),
    )
    if getattr(sys, "frozen", False):
        scoreboard_command = [
            sys.executable,
            "--data-dir",
            str(config.data_dir),
            "--scoreboard-child",
        ]
    else:
        scoreboard_command = [
            sys.executable,
            "-m",
            "screamingface._runtime.cli",
            "--data-dir",
            str(config.data_dir),
            "_scoreboard",
        ]
    scoreboard = subprocess.Popen(scoreboard_command)
    try:
        await _supervise(servers, scoreboard=scoreboard)
    finally:
        if scoreboard.poll() is None:
            scoreboard.terminate()
            await asyncio.to_thread(scoreboard.wait)


async def _migrate(config: RuntimeConfig) -> None:
    from aigateway.db import build_tortoise_config as gateway_tortoise_config
    from scoreboard.db import build_tortoise_config as scoreboard_tortoise_config
    from tortoise import Tortoise  # pyright: ignore[reportMissingImports]
    from tortoise.migrations.api import migrate  # pyright: ignore[reportMissingImports]

    for database_url, tortoise_config in (
        (config.gateway_database_url, gateway_tortoise_config),
        (config.scoreboard_database_url, scoreboard_tortoise_config),
    ):
        try:
            await migrate(config=tortoise_config(database_url))
        finally:
            await Tortoise.close_connections()


def _build_apps(config: RuntimeConfig) -> tuple[object, object]:
    from aigateway.config import Settings as GatewaySettings
    from aigateway.main import create_app as create_gateway_app
    from pydantic import SecretStr  # pyright: ignore[reportMissingImports]
    from url4_cloud import job_env
    from url4_cloud.config import Settings as EngineSettings
    from url4_cloud.local import create_local_app

    gateway = create_gateway_app(
        GatewaySettings(
            host="127.0.0.1",
            port=9105,
            database_url=SecretStr(config.gateway_database_url),
            auth_mode="disabled",
        )
    )
    run_env: Mapping[str, str] = {
        **os.environ,
        job_env.RUNNER_CONFIG: str(config.runner_config),
        "URL4_BENCHMARK_ASSETS": str(config.assets_dir),
    }
    engine = create_local_app(
        settings=EngineSettings(aigateway_base_url=SERVICES["gateway"]),
        env=run_env,
    )
    return gateway, engine


def run_scoreboard(config: RuntimeConfig) -> None:
    portal_dir, artifacts_dir = scoreboard_assets()
    os.environ.setdefault("SCOREBOARD_PORTAL_DIR", str(portal_dir))
    os.environ.setdefault("SCOREBOARD_PORTAL_ARTIFACTS_DIR", str(artifacts_dir))
    os.environ["SCOREBOARD_DATABASE_URL"] = config.scoreboard_database_url

    import uvicorn  # pyright: ignore[reportMissingImports]
    from scoreboard.config import Settings
    from scoreboard.main import create_app
    from scoreboard.seed import _run

    asyncio.run(
        _run(
            json.dumps(
                [
                    {
                        "id": "draco/smoke",
                        "display_name": "DRACO Smoke",
                        "description": "Local end-to-end development protocol",
                    }
                ]
            )
        )
    )
    settings = Settings(
        host="127.0.0.1",
        port=9106,
        database_url=config.scoreboard_database_url,
        auth_mode="disabled",
        portal_dir=portal_dir,
        portal_artifacts_dir=artifacts_dir,
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=9106, log_level="info")


def _server(app: object, port: int, name: str) -> Server:
    import uvicorn  # pyright: ignore[reportMissingImports]

    return _EmbeddedServer(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", lifespan="on"),
        name=name,
    )


def _embedded_server_type():
    import uvicorn  # pyright: ignore[reportMissingImports]

    class EmbeddedServer(uvicorn.Server):
        def __init__(self, config, *, name: str) -> None:
            super().__init__(config)
            self.name = name

        async def startup(self, sockets=None) -> None:
            try:
                await super().startup(sockets=sockets)
            except SystemExit as exc:
                raise RuntimeError(
                    f"{self.name} could not listen on {self.config.host}:{self.config.port}"
                ) from exc

        @contextlib.contextmanager
        def capture_signals(self) -> Iterator[None]:
            yield

    return EmbeddedServer


_EmbeddedServer = _embedded_server_type()


async def _supervise(  # noqa: PLR0915
    servers: tuple[Server, ...], *, scoreboard: subprocess.Popen[bytes]
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    with _signal_handlers(loop, stop):
        tasks = tuple(asyncio.create_task(server.serve()) for server in servers)
        stop_task = asyncio.create_task(stop.wait())
        try:
            async with asyncio.timeout(STARTUP_TIMEOUT_SECONDS):
                while not all(server.started for server in servers) or not _port_open(9106):
                    if scoreboard.poll() is not None:
                        raise RuntimeError("Scoreboard stopped during startup")
                    failed = next((task for task in tasks if task.done()), None)
                    if failed is not None:
                        exception = failed.exception()
                        raise RuntimeError("runtime service stopped during startup") from exception
                    await asyncio.sleep(0.01)
            print(
                "SCREAMINGFACE_RUNTIME_READY "
                + json.dumps({"services": SERVICES}, separators=(",", ":"), sort_keys=True),
                flush=True,
            )
            scoreboard_task = asyncio.create_task(asyncio.to_thread(scoreboard.wait))
            done, _ = await asyncio.wait(
                (*tasks, stop_task, scoreboard_task), return_when=asyncio.FIRST_COMPLETED
            )
            if stop_task not in done:
                if scoreboard_task in done:
                    raise RuntimeError("Scoreboard stopped unexpectedly")
                failed = next(task for task in tasks if task in done)
                exception = failed.exception()
                raise RuntimeError("a runtime service stopped unexpectedly") from exception
        finally:
            for server in servers:
                server.should_exit = True
            await asyncio.gather(*tasks, return_exceptions=True)
            stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_task


def _port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


@contextlib.contextmanager
def _signal_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> Iterator[None]:
    previous: dict[signal.Signals, Any] = {}

    def handle(_signum: int, _frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop.set)

    for selected in (signal.SIGINT, signal.SIGTERM):
        previous[selected] = signal.signal(selected, handle)
    try:
        yield
    finally:
        for selected, handler in previous.items():
            signal.signal(selected, handler)
