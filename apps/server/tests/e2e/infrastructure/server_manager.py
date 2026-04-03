"""Manages an SF server subprocess for e2e tests."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .log_collector import LogCollector

SERVER_DIR = Path(__file__).resolve().parents[3]  # apps/server/


class ServerManager:
    """Start, monitor, and stop an SF server subprocess."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        session_id: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._session_id = session_id
        self._env_extra = env_extra or {}
        self._proc: subprocess.Popen | None = None
        self._logs: LogCollector | None = None
        self._ready_info: dict[str, Any] = {}

    def start(self, timeout: float = 30) -> dict[str, Any]:
        """Start the server subprocess and wait for the ready event.

        Returns the parsed ready-event dict (contains host, port, pid, etc.).
        Raises ``RuntimeError`` if the server does not become ready.
        """
        env = {**os.environ, "_SF_SUBPROCESS": "1"}
        env.update(self._env_extra)
        if self._session_id:
            env["_SF_SESSION_ID"] = self._session_id

        cmd = [
            "sf",
            "run",
            "--no-ssl",
            "--no-reload",
            "--config-json",
            json.dumps(self._config),
        ]

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(SERVER_DIR),
        )
        self._logs = LogCollector(self._proc)

        ready = self._logs.wait_for_ready(timeout=timeout)
        if not ready:
            last_lines = "\n".join(self._logs.dump_last())
            self.stop()
            raise RuntimeError(
                f"Server did not emit ready event within {timeout}s.\nLast log lines:\n{last_lines}"
            )

        self._ready_info = ready
        return ready

    def stop(self, timeout: float = 10) -> None:
        """Stop the server subprocess gracefully (SIGTERM → SIGKILL)."""
        if self._proc is None:
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
            self._proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            self._proc.kill()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self._proc = None

    @property
    def base_url(self) -> str:
        host = self._ready_info.get("host", "0.0.0.0")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = self._ready_info.get("port", 8000)
        scheme = self._ready_info.get("scheme", "http")
        return f"{scheme}://{host}:{port}"

    @property
    def logs(self) -> LogCollector:
        assert self._logs is not None, "Server not started"
        return self._logs

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @staticmethod
    def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 15) -> bool:
        """Poll until a TCP port is accepting connections."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex((host, port)) == 0:
                    return True
            time.sleep(0.2)
        return False

    @staticmethod
    def find_free_port() -> int:
        """Bind to port 0 and return the OS-assigned port number."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def __enter__(self) -> ServerManager:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
