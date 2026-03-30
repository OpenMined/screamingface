"""Live E2E tests for url4 resolution and intent dispatch.

Starts the real server, makes real HTTP requests, and checks that URL4
expression resolution and backend dispatch work end-to-end. No mocks.

Run: cd apps/server && uv run python tests/test_e2e_url4.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx

SERVER_DIR = Path(__file__).resolve().parents[5]  # apps/server/
SERVER_CMD = [
    "sf",
    "run",
    "--no-ssl",
    "--no-reload",
    "--disable",
    "claude-intercept",
    "--disable",
    "mitmproxy-intercept",
    "--disable",
    "claude-env-intercept",
]

TIMEOUT = 5


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

    def wait_for_ready(self, timeout: float = 30) -> dict | None:
        """Block until the JSON ready event appears, return parsed dict or None."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                for line in self.lines:
                    if '"event"' in line and '"ready"' in line:
                        try:
                            return json.loads(line)
                        except json.JSONDecodeError:
                            continue
            time.sleep(0.3)
        return None

    def dump_all(self) -> list[str]:
        with self._lock:
            return list(self.lines)


def check(
    name: str,
    client: httpx.Client,
    *,
    path: str = "/url4",
    params: dict | None = None,
    expect_status: int = 200,
    expect_contains: str | None = None,
    expect_not_empty: bool = False,
    timeout: float = TIMEOUT,
) -> tuple[str, bool, str]:
    """Run a single GET check. Returns (name, passed, detail)."""
    try:
        resp = client.get(path, params=params, timeout=timeout)
    except httpx.TimeoutException:
        return (name, False, f"timeout after {timeout}s")
    except Exception as exc:
        return (name, False, f"request error: {exc}")

    if resp.status_code != expect_status:
        body = resp.text[:200]
        return (name, False, f"status {resp.status_code}, expected {expect_status} — body: {body}")

    if expect_contains is not None and expect_contains not in resp.text:
        return (name, False, f"body missing {expect_contains!r}: {resp.text[:200]}")

    if expect_not_empty and not resp.text.strip():
        return (name, False, "response body is empty")

    return (name, True, f"ok — {resp.text[:100]}")


def main() -> int:
    has_claude = shutil.which("claude") is not None
    print("=== E2E URL4 Tests ===\n")
    print(f"  Claude CLI available: {has_claude}")

    # 1. Start server
    print("\n[1/4] Starting SF server (no-ssl, no-reload)...")
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
        # 2. Wait for ready event
        print("[2/4] Waiting for server ready...")
        ready = logs.wait_for_ready(timeout=30)
        if not ready:
            print("ERROR: Server did not emit ready event within 30s")
            print("       Last 20 log lines:")
            for line in logs.dump_all()[-20:]:
                print(f"         {line}")
            return 1

        host = ready.get("host", "0.0.0.0")
        if host == "0.0.0.0":
            host = "localhost"
        port = ready["port"]
        scheme = ready.get("scheme", "http")
        base = f"{scheme}://{host}:{port}"
        print(f"       Server ready at {base} (pid {ready.get('pid')})")

        # 3. Run checks
        print("[3/4] Running checks...\n")
        client = httpx.Client(base_url=base, verify=False)
        results: list[tuple[str, bool, str]] = []

        # --- Basic url4 resolution (no backend needed) ---

        results.append(
            check(
                "resolve_plain_text",
                client,
                params={"q": "hello"},
                expect_status=200,
                expect_contains="hello",
            )
        )

        results.append(
            check(
                "missing_q_rejected",
                client,
                params={"context": "hello"},
                expect_status=400,
            )
        )

        results.append(
            check(
                "intent_non_url_rejected",
                client,
                params={"q": "hello!echo"},
                expect_status=400,
            )
        )

        # --- Intent dispatch to claude-backend (requires Claude CLI) ---

        if has_claude:
            backend_url = f"{base}/claude/default"
            prompt = "respond with exactly: E2E_OK"

            # Simple: plain text context → backend
            intent_url = f"{backend_url}?prompt={quote(prompt)}"
            results.append(
                check(
                    "intent_dispatch_to_claude",
                    client,
                    params={"q": f"hello!{intent_url}"},
                    expect_status=200,
                    expect_not_empty=True,
                    timeout=60,
                )
            )

            # With fetched resource context → backend
            # Use the server's own /health endpoint as a fetchable resource
            health_url = f"{base}/health"
            intent_url2 = f"{backend_url}?prompt={quote('describe what you see in one sentence')}"
            results.append(
                check(
                    "intent_fetch_then_dispatch",
                    client,
                    params={"q": f"({health_url})!{intent_url2}"},
                    expect_status=200,
                    expect_not_empty=True,
                    timeout=60,
                )
            )
        else:
            print("  [SKIP] intent_dispatch_to_claude — Claude CLI not found")
            print("  [SKIP] intent_fetch_then_dispatch — Claude CLI not found")

        client.close()

    finally:
        # 4. Teardown
        print("\n[4/4] Shutting down server...")
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    # Report
    print("\n=== Results ===")
    all_pass = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        suffix = "" if detail == "ok" else f" — {detail}"
        print(f"  [{status}] {name}{suffix}")

    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
