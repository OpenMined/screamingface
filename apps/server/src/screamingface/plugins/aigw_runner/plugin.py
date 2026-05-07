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
        default=10.0,
        description="Max seconds to wait after Popen before declaring failure.",
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

        if shutil.which("uv") is None:
            return False, "`uv` command not found in PATH — required to run the gateway"

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

        cmd = [
            "uv",
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
        env = os.environ.copy()
        logger.info("aigw-runner: spawning gateway: %s", " ".join(cmd))

        self._process = subprocess.Popen(  # noqa: S603
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        time.sleep(0.5)
        retcode = self._process.poll()
        if retcode is not None:
            output = self._process.stdout.read() if self._process.stdout else ""
            self._process = None
            raise RuntimeError(
                f"aigw-runner: gateway exited immediately (code {retcode}):\n{output}"
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
