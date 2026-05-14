"""aigw-runner — owns the apps/aigateway/ uvicorn subprocess.

When SF starts, this plugin spawns the gateway as a child process so
url4 backend calls routed through aigw_*_backend plugins have a
gateway to talk to. When SF shuts down (via app.shutdown hook or
atexit), the gateway is terminated gracefully.

Mirrors the mitmproxy_intercept lifecycle pattern: Popen + daemon
thread streaming stdout into the SF logger + dual teardown via
hook and atexit.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class AigwRunnerSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_RUNNER__",
        env_nested_delimiter="__",
    )

    port: int = Field(
        default=9105,
        description="Port the gateway uvicorn listens on.",
    )
    aigateway_dir: str | None = Field(
        default=None,
        description=(
            "Filesystem path to apps/aigateway/. If unset, resolves "
            "relative to this server's working directory: ../aigateway."
        ),
    )
    startup_timeout_seconds: float = Field(
        default=15.0,
        description="Max seconds to wait after Popen before declaring failure.",
    )
    migrations_timeout_seconds: float = Field(
        default=30.0,
        description="Max seconds to wait for gateway database migrations.",
    )
    database_path: str | None = Field(
        default=None,
        description=(
            "SQLite database path for the local gateway. If unset, resolves "
            "to .sf/aigateway.db under the SF working directory."
        ),
    )
    uv_bin: str | None = Field(
        default=None,
        description="Explicit uv executable path. If unset, uv is resolved from PATH.",
    )
    auth_enabled: bool = Field(
        default=False,
        description="Whether the spawned local gateway should enforce its own bearer auth.",
    )
    enabled: bool = Field(
        default=True,
        description=(
            "When False, the runner skips spawning the gateway. Useful "
            "in tests / dev where the gateway is already running."
        ),
    )


class AigwRunnerPlugin(Plugin):
    name = "aigw-runner"
    description = "Spawns the apps/aigateway/ uvicorn subprocess alongside SF."
    tags: list[str] = ["product:aigw", "product:system"]
    depends: list[str] = []
    conflicts: list[str] = []
    settings_class = AigwRunnerSettings

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._aigateway_dir: Path | None = None
        self._uv_bin: str | None = None

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason

        settings: AigwRunnerSettings = self.settings  # type: ignore[assignment]
        if not settings.enabled:
            return True, ""

        # Resolve the apps/aigateway directory.
        if settings.aigateway_dir is not None:
            candidate = Path(settings.aigateway_dir).expanduser().resolve()
        else:
            # Default: SF runs from apps/server/, so apps/aigateway is ../aigateway
            candidate = (Path.cwd() / ".." / "aigateway").resolve()

        if not candidate.exists():
            return False, f"aigateway directory not found at {candidate}"
        if not (candidate / "pyproject.toml").exists():
            return False, f"{candidate} does not look like a uv project (no pyproject.toml)"

        self._aigateway_dir = candidate

        uv_bin = settings.uv_bin or shutil.which("uv")
        if uv_bin is None:
            return False, "`uv` command not found in PATH — required to run the gateway"
        self._uv_bin = uv_bin

        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,  # noqa: ARG002
        routes: RouteRegistry,  # noqa: ARG002
    ) -> None:
        settings: AigwRunnerSettings = self.settings  # type: ignore[assignment]

        if not settings.enabled:
            logger.info("aigw-runner: disabled via settings.enabled=False; skipping spawn")
            return

        assert self._aigateway_dir is not None  # set in preflight
        assert self._uv_bin is not None  # set in preflight

        database_url = _database_url(settings)
        env = _gateway_env(settings, database_url)
        migrate_cmd = [
            self._uv_bin,
            "run",
            "--directory",
            str(self._aigateway_dir),
            "python",
            "-m",
            "tortoise",
            "-c",
            "aigateway.db.TORTOISE_CONFIG",
            "migrate",
        ]
        logger.info("aigw-runner: running gateway migrations: %s", " ".join(migrate_cmd))
        try:
            migration = subprocess.run(  # noqa: S603
                migrate_cmd,
                env=env,
                cwd=str(self._aigateway_dir),
                timeout=settings.migrations_timeout_seconds,
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("aigw-runner: gateway migrations timed out") from exc
        if migration.returncode != 0:
            raise RuntimeError(
                "aigw-runner: gateway migrations failed "
                f"(code {migration.returncode}):\n{migration.stdout}{migration.stderr}"
            )

        cmd = [
            self._uv_bin,
            "run",
            "--directory",
            str(self._aigateway_dir),
            "uvicorn",
            "aigateway.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(settings.port),
            "--log-level",
            "info",
        ]
        logger.info("aigw-runner: spawning gateway: %s", " ".join(cmd))

        self._process = subprocess.Popen(  # noqa: S603
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        health_url = f"http://127.0.0.1:{settings.port}/healthz"
        if not _wait_for_health(self._process, health_url, settings.startup_timeout_seconds):
            retcode = self._process.poll()
            output = self._process.stdout.read() if self._process.stdout else ""
            self._stop()
            if retcode is not None:
                raise RuntimeError(
                    f"aigw-runner: gateway exited immediately (code {retcode}):\n{output}"
                )
            raise RuntimeError(
                f"aigw-runner: gateway did not become healthy at {health_url} "
                f"within {settings.startup_timeout_seconds}s:\n{output}"
            )

        threading.Thread(
            target=_log_output, args=(self._process,), daemon=True, name="aigw-runner-log"
        ).start()

        atexit.register(self._stop)
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)
        logger.info(
            "aigw-runner: gateway running on port %d (PID %d)", settings.port, self._process.pid
        )

    async def _on_shutdown(self) -> None:
        self._stop()

    def teardown(self) -> None:
        self._stop()

    def _stop(self) -> None:
        try:
            atexit.unregister(self._stop)
        except Exception:  # pragma: no cover
            pass
        if self._process is None:
            return
        logger.info("aigw-runner: stopping gateway (PID %d)...", self._process.pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("aigw-runner: gateway did not terminate in 5s — killing")
            self._process.kill()
            self._process.wait(timeout=3)
        self._process = None


def _log_output(proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            logger.info("[aigateway] %s", line)


def _database_url(settings: AigwRunnerSettings) -> str:
    if settings.database_path is not None:
        path = Path(settings.database_path).expanduser().resolve()
    else:
        path = (Path.cwd() / ".sf" / "aigateway.db").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite://{path}"


def _gateway_env(settings: AigwRunnerSettings, database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["AIGATEWAY_DATABASE_URL"] = database_url
    env["AIGATEWAY_AUTH_ENABLED"] = "true" if settings.auth_enabled else "false"
    return env


def _wait_for_health(proc: subprocess.Popen, url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            resp = httpx.get(url, timeout=0.5)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False
