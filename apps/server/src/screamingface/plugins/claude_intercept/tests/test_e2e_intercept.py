"""Live E2E test for mitmproxy traffic interception.

Requires: sudo access, Claude CLI in PATH (authenticated via OAuth).
Run: cd apps/server && uv run python tests/test_e2e_intercept.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

TIMEOUT = 60  # total test timeout in seconds
SERVER_CMD = ["sf", "run"]
CLAUDE_CMD = ["claude", "-p", "Say exactly: E2E_TEST_OK", "--output-format", "text"]
SERVER_DIR = Path(__file__).resolve().parents[5]  # apps/server/


class LogCollector:
    """Thread-safe collector that reads subprocess output and stores lines."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.lines: list[str] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._read, args=(proc,), daemon=True)
        self._thread.start()

    def _read(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            with self._lock:
                self.lines.append(line)

    def wait_for(self, marker: str, timeout: float = 30) -> bool:
        """Block until a log line containing marker appears, or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if any(marker in line for line in self.lines):
                    return True
            time.sleep(0.5)
        return False

    def get_traces(self) -> list[str]:
        """Return all [E2E-TRACE] lines."""
        with self._lock:
            return [line for line in self.lines if "[E2E-TRACE]" in line]

    def dump_all(self) -> list[str]:
        """Return all collected lines (for debugging failures)."""
        with self._lock:
            return list(self.lines)


def main() -> int:
    print("=== E2E Interception Test ===\n")

    # 1. Start SF server
    print("[1/5] Starting SF server...")
    server = subprocess.Popen(
        SERVER_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "_SF_SUBPROCESS": "1"},
        cwd=str(SERVER_DIR),
    )
    logs = LogCollector(server)

    try:
        # 2. Wait for server + mitmproxy ready
        print("[2/5] Waiting for server ready (enter sudo password when prompted)...")
        if not logs.wait_for("Mitmproxy started", timeout=45):
            print("ERROR: Server/mitmproxy did not start within 45s")
            print("       Last 20 log lines:")
            for line in logs.dump_all()[-20:]:
                print(f"         {line}")
            return 1
        print("       Server + mitmproxy ready!")

        # Brief pause for mitmproxy to fully initialize interception
        time.sleep(2)

        # 3. Run Claude CLI
        print("[3/5] Running Claude CLI...")
        try:
            result = subprocess.run(
                CLAUDE_CMD,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
            claude_output = result.stdout.strip()
            print(f"       Claude output: {claude_output!r}")
            if result.returncode != 0:
                print(f"       Claude stderr: {result.stderr.strip()!r}")
        except subprocess.TimeoutExpired:
            print(f"ERROR: Claude CLI timed out after {TIMEOUT}s")
            claude_output = ""

        # Small delay to let log lines flush
        time.sleep(1)

        # 4. Check traces
        print("[4/5] Checking interception traces...")
        traces = logs.get_traces()
        if traces:
            for t in traces:
                print(f"       {t}")
        else:
            print("       (no [E2E-TRACE] lines found)")
            print("       Last 30 log lines:")
            for line in logs.dump_all()[-30:]:
                print(f"         {line}")

        checks = {
            "mitmproxy_started": any("MITMPROXY" in t for t in traces),
            "addon_intercepted": any("ADDON intercepted" in t for t in traces),
            "proxy_received": any("PROXY received" in t for t in traces),
            "proxy_responded": any("PROXY response" in t for t in traces),
            "claude_output_ok": "E2E_TEST_OK" in claude_output,
        }

    finally:
        # 5. Teardown
        print("[5/5] Shutting down server...")
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        # Also kill any sudo mitmproxy that may linger
        subprocess.run(["sudo", "pkill", "-f", "mitmdump"], capture_output=True)

    # Report
    print("\n=== Results ===")
    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}")

    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
