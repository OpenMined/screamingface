"""Live E2E test for claude-frontend proxy with real url4 context injection.

Starts the real server with:
  - url4-spec "httpbin-robots" → fetches https://httpbin.org/robots.txt
  - claude-frontend upstream → https://httpbin.org/anything (echoes request body)

Verifies that the cached url4 content ("User-agent") appears in the system
prompt of the forwarded /v1/messages request.

Run: cd apps/server && uv run python tests/test_e2e_claude_frontend.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

SERVER_DIR = Path(__file__).resolve().parents[5]  # apps/server/

# Inline config: only enable the plugins we need, point upstream at httpbin
E2E_CONFIG = json.dumps(
    {
        "version": "0.1.0",
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False,
            "ssl": False,
        },
        "plugins": [
            "url4-executor",
            "url4-specs",
            "claude-frontend",
        ],
        "plugin_config": {
            "claude-frontend": {
                "active_spec": "httpbin-robots",
                "upstream_url": "https://httpbin.org/anything",
                "listen_host": "127.0.0.1",
                "listen_port": 9101,
            },
            "url4-specs": {
                "specs": {
                    "httpbin-robots": {
                        "expression": "(https://httpbin.org/robots.txt)!"
                        "'You are an API testing assistant'",
                    },
                },
            },
        },
    }
)

SERVER_CMD = [
    "sf",
    "run",
    "--no-ssl",
    "--no-reload",
    "--config-json",
    E2E_CONFIG,
]

PROXY_BASE = "http://127.0.0.1:9101"
TIMEOUT = 15


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

    def find_line(self, needle: str) -> str | None:
        with self._lock:
            for line in self.lines:
                if needle in line:
                    return line
        return None

    def dump_all(self) -> list[str]:
        with self._lock:
            return list(self.lines)


def wait_for_proxy(host: str = "127.0.0.1", port: int = 9101, timeout: float = 10) -> bool:
    """Wait for the claude-frontend proxy port to be listening."""
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def main() -> int:
    print("=== E2E Claude Frontend Tests ===\n")

    # 1. Start server
    print("[1/4] Starting SF server with inline config...")
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
        # 2. Wait for ready
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
        print(f"       Server ready at http://{host}:{port} (pid {ready.get('pid')})")

        # Check for cached context in logs
        cached_line = logs.find_line("Cached")
        if cached_line:
            print(f"       {cached_line.strip()}")
        else:
            print("       WARNING: No 'Cached' log line found (context may not have resolved)")

        # Wait for proxy port
        if not wait_for_proxy():
            print("ERROR: claude-frontend proxy not listening on :9101 within 10s")
            return 1
        print(f"       Proxy listening at {PROXY_BASE}")

        # 3. Run checks
        print("[3/4] Running checks...\n")
        results: list[tuple[str, bool, str]] = []

        # --- Check 1: Context injection with string system prompt ---
        try:
            resp = httpx.post(
                f"{PROXY_BASE}/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "system": "Be helpful",
                },
                headers={"x-api-key": "test-key"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                echoed = resp.json()
                # httpbin echoes the POST body under "json" key
                forwarded_body = echoed.get("json", {})
                system_prompt = forwarded_body.get("system", "")

                has_robots = "User-agent" in str(system_prompt)
                has_original = "Be helpful" in str(system_prompt)
                has_intent = "API testing assistant" in str(system_prompt)

                sys_str = str(system_prompt)[:150]
                name = "context_injection_string_system"
                if has_robots and has_original and has_intent:
                    results.append((name, True, f"all present — {sys_str}"))
                elif has_robots and has_original:
                    results.append((name, False, f"src+orig but no intent — {sys_str}"))
                elif has_robots:
                    results.append((name, False, f"sources only — {sys_str}"))
                elif has_original:
                    results.append((name, False, f"original only — {sys_str}"))
                else:
                    results.append((name, False, f"neither found — {sys_str}"))
            else:
                results.append(
                    (
                        "context_injection_string_system",
                        False,
                        f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    )
                )
        except Exception as exc:
            results.append(("context_injection_string_system", False, f"request error: {exc}"))

        # --- Check 2: Context injection with no system prompt ---
        try:
            resp = httpx.post(
                f"{PROXY_BASE}/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test-key"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                echoed = resp.json()
                forwarded_body = echoed.get("json", {})
                system_prompt = forwarded_body.get("system", "")

                sp = str(system_prompt)
                has_src = "User-agent" in sp
                has_int = "API testing assistant" in sp
                if has_src and has_int:
                    results.append(
                        ("context_injection_no_system", True, f"both intent+source — {sp[:100]}")
                    )
                else:
                    results.append(
                        (
                            "context_injection_no_system",
                            False,
                            f"missing src={has_src} int={has_int} — {sp[:150]}",
                        )
                    )
            else:
                results.append(
                    (
                        "context_injection_no_system",
                        False,
                        f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    )
                )
        except Exception as exc:
            results.append(("context_injection_no_system", False, f"request error: {exc}"))

        # --- Check 3: Extra fields pass through ---
        try:
            resp = httpx.post(
                f"{PROXY_BASE}/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "custom_field": "should_survive",
                },
                headers={"x-api-key": "test-key"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                echoed = resp.json()
                forwarded_body = echoed.get("json", {})
                if forwarded_body.get("custom_field") == "should_survive":
                    results.append(("extra_fields_passthrough", True, "custom_field preserved"))
                else:
                    results.append(
                        (
                            "extra_fields_passthrough",
                            False,
                            f"custom_field lost — body: {json.dumps(forwarded_body)[:200]}",
                        )
                    )
            else:
                results.append(
                    (
                        "extra_fields_passthrough",
                        False,
                        f"unexpected status {resp.status_code}",
                    )
                )
        except Exception as exc:
            results.append(("extra_fields_passthrough", False, f"request error: {exc}"))

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
        print(f"  [{status}] {name} — {detail}")

    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
