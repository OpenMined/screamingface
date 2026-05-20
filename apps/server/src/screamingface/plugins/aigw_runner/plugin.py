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
import signal
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.aigw_base.config import (
    gateway_port_from_url,
    is_runner_disabled,
    resolve_aigw_runtime_config,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)

DEFAULT_AIGATEWAY_DIR = "../aigateway"
DEFAULT_DATABASE_PATH = ".sf/aigateway.db"
DEFAULT_UV_BIN = "uv"


class AigwRunnerSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_RUNNER__",
        env_nested_delimiter="__",
    )

    port: int = Field(
        default=9105,
        description="Deprecated compatibility field; prefer aigw-base.gateway_url.",
    )
    aigateway_dir: str = Field(
        default=DEFAULT_AIGATEWAY_DIR,
        description=(
            "Filesystem path to apps/aigateway/. Optional; defaults to ../aigateway "
            "relative to this server's working directory."
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
    database_path: str = Field(
        default=DEFAULT_DATABASE_PATH,
        description=(
            "SQLite database path for the local gateway. Optional; defaults to "
            ".sf/aigateway.db under the SF working directory."
        ),
    )
    uv_bin: str = Field(
        default=DEFAULT_UV_BIN,
        description="Explicit uv executable path. Optional; defaults to uv resolved from PATH.",
    )
    auth_enabled: bool = Field(
        default=False,
        description="Deprecated compatibility field; local managed mode always disables auth.",
    )
    enabled: bool = Field(
        default=True,
        description=(
            "When False, the runner skips spawning the gateway. Useful "
            "in tests / dev where the gateway is already running."
        ),
    )

    @field_validator("aigateway_dir", "database_path", "uv_bin", mode="before")
    @classmethod
    def _default_optional_strings(cls, value: object, info: ValidationInfo) -> object:
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
        defaults = {
            "aigateway_dir": DEFAULT_AIGATEWAY_DIR,
            "database_path": DEFAULT_DATABASE_PATH,
            "uv_bin": DEFAULT_UV_BIN,
        }
        return defaults.get(info.field_name or "", value)


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
        if is_runner_disabled():
            return True, ""
        if not settings.enabled:
            return True, ""
        app = getattr(self, "_activation_app", None)
        if app is not None and resolve_aigw_runtime_config(app).mode == "external":
            return True, ""
        return self._resolve_local_gateway(settings)

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,  # noqa: ARG002
        routes: RouteRegistry,  # noqa: ARG002
    ) -> None:
        settings: AigwRunnerSettings = self.settings  # type: ignore[assignment]
        self._app = app

        runtime_config = resolve_aigw_runtime_config(app)
        if is_runner_disabled():
            logger.info("aigw-runner: disabled via SF_AIGW_RUNNER_DISABLED=1; skipping spawn")
            return
        if not settings.enabled:
            logger.info(
                "aigw-runner: disabled via deprecated settings.enabled=False; skipping spawn"
            )
            return
        if runtime_config.mode == "external":
            logger.info("aigw-runner: external mode; skipping local gateway spawn")
            return

        ok, reason = self._resolve_local_gateway(settings)
        if not ok:
            raise RuntimeError(reason)

        assert self._aigateway_dir is not None  # set by _resolve_local_gateway
        assert self._uv_bin is not None  # set by _resolve_local_gateway
        port = gateway_port_from_url(runtime_config.gateway_url, settings.port)
        if _is_port_open("127.0.0.1", port):
            existing_status = _existing_local_gateway_status(runtime_config.gateway_url)
            if existing_status == "local_no_auth":
                logger.warning(
                    "aigw-runner: stopping stale local no-auth gateway on port %d before spawn",
                    port,
                )
                if not _terminate_processes_on_port(port):
                    raise RuntimeError(
                        f"aigw-runner: port {port} is already used by a local no-auth "
                        "AIGateway, but the runner could not stop it"
                    )
            elif existing_status == "auth_enabled":
                raise RuntimeError(
                    f"aigw-runner: port {port} is already used by an auth-enabled AIGateway; "
                    "stop it before using local-managed mode, or set aigw-base.mode=external"
                )
            else:
                raise RuntimeError(
                    f"aigw-runner: port {port} is already in use but does not look like "
                    "a local no-auth AIGateway"
                )

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
            str(port),
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
        startup_output: deque[str] = deque(maxlen=200)
        threading.Thread(
            target=_log_output,
            args=(self._process, startup_output),
            daemon=True,
            name="aigw-runner-log",
        ).start()

        health_url = f"http://127.0.0.1:{port}/healthz"
        if not _wait_for_health(self._process, health_url, settings.startup_timeout_seconds):
            retcode = self._process.poll()
            if retcode is not None:
                output = "\n".join(startup_output)
                self._process = None
                raise RuntimeError(
                    f"aigw-runner: gateway exited immediately (code {retcode}):\n{output}"
                )
            self._stop()
            raise RuntimeError(
                f"aigw-runner: gateway did not become healthy at {health_url} "
                f"within {settings.startup_timeout_seconds}s"
            )

        atexit.register(self._stop)
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)
        logger.info("aigw-runner: gateway running on port %d (PID %d)", port, self._process.pid)

    def customize_schema(self, schema: dict) -> dict:
        props = schema.setdefault("properties", {})
        for deprecated in ("auth_enabled", "enabled", "port"):
            props.pop(deprecated, None)
        required = schema.get("required")
        if isinstance(required, list):
            for deprecated in ("auth_enabled", "enabled", "port"):
                if deprecated in required:
                    required.remove(deprecated)
        return schema

    async def _on_shutdown(self) -> None:
        self._stop()

    def teardown(self) -> None:
        self._stop()

    def _resolve_local_gateway(self, settings: AigwRunnerSettings) -> tuple[bool, str]:
        candidate = Path(settings.aigateway_dir).expanduser().resolve()
        if not candidate.exists():
            return False, f"aigateway directory not found at {candidate}"
        if not (candidate / "pyproject.toml").exists():
            return False, f"{candidate} does not look like a uv project (no pyproject.toml)"
        self._aigateway_dir = candidate

        uv_bin: str | None = settings.uv_bin
        if uv_bin == DEFAULT_UV_BIN:
            uv_bin = shutil.which(DEFAULT_UV_BIN)
        if uv_bin is None:
            return False, "`uv` command not found in PATH — required to run the gateway"
        self._uv_bin = uv_bin
        return True, ""

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


def _log_output(proc: subprocess.Popen, startup_output: deque[str] | None = None) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            if startup_output is not None:
                startup_output.append(line)
            logger.info("[aigateway] %s", line)


def _database_url(settings: AigwRunnerSettings) -> str:
    path = Path(settings.database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite://{path}"


def _gateway_env(settings: AigwRunnerSettings, database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["AIGATEWAY_DATABASE_URL"] = database_url
    env["AIGATEWAY_AUTH_ENABLED"] = "false"
    return env


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _existing_local_gateway_status(gateway_url: str) -> str:
    base = gateway_url.rstrip("/")
    try:
        health = httpx.get(f"{base}/healthz", timeout=0.5)
        if health.status_code != 200:
            return "not_gateway"
        auth = httpx.get(f"{base}/v1/auth/me", timeout=0.5)
    except httpx.HTTPError:
        return "not_gateway"
    if auth.status_code == 200:
        return "local_no_auth"
    if auth.status_code == 401:
        return "auth_enabled"
    return "misconfigured"


def _pids_listening_on_port(port: int) -> list[int]:
    lsof = shutil.which("lsof")
    if lsof is None:
        return []
    result = subprocess.run(  # noqa: S603
        [lsof, "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return pids


def _terminate_processes_on_port(port: int) -> bool:
    pids = _pids_listening_on_port(port)
    if not pids:
        return False

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            return False

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not _is_port_open("127.0.0.1", port):
            return True
        time.sleep(0.1)

    sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
    for pid in pids:
        try:
            os.kill(pid, sigkill)
        except ProcessLookupError:
            pass
        except PermissionError:
            return False
    time.sleep(0.2)
    return not _is_port_open("127.0.0.1", port)


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
