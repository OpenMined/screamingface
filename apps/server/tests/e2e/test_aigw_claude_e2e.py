"""End-to-end test for the full claude-frontend → aigw-claude-backend → AI Gateway → Anthropic chain.

The test stands up a session SF server with these plugins active:

- ``claude-frontend`` — the listener that emulates Anthropic's API surface
- ``url4-executor`` + ``url4-specs`` — resolves the configured spec
- ``aigw-base`` + ``aigw-claude-backend`` — handles the ``/claude`` backend call
  by POSTing to the gateway
- ``aigw-runner`` — spawns the apps/aigateway/ uvicorn subprocess

A url4 spec maps ``$prompt`` → ``/claude?q=$prompt``, which forces the
url4 executor to call the gateway-backed ``/claude`` endpoint instead of
forwarding the user prompt straight to upstream. The full chain:

    ClaudeCodeClient (test)
        → claude-frontend (port: proxy_port)
        → url4-executor (resolves $prompt, sees /claude backend call)
        → aigw-claude-backend (POSTs OpenAI ChatCompletions to localhost:9105)
        → aigw-runner subprocess (apps/aigateway uvicorn on 9105)
        → real api.anthropic.com (live, OAuth via gateway profile)

Skipped unless ANTHROPIC_API_KEY is set OR the Claude Code CLI keychain
entry exists locally — the gateway's bootstrap accepts either.

Asserts on TWO levels:

1. **Round-trip:** the user message gets a non-empty assistant response
   substituted into it (via httpbin echo upstream — same pattern as
   test_cat_breeds_spec.py).
2. **Span chain:** OTLP collector sees the four expected layers fire
   (claude-frontend, url4 resolve, aigw-claude-backend run, gateway
   POST). Catches silent layer-skipping if anyone re-routes /claude.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_live]

# url4 spec: substitute $prompt as the q-param of a /claude backend call.
# The /claude endpoint is served by aigw-claude-backend; the result text is
# substituted back into the user message before claude-frontend forwards
# the request to its upstream (httpbin echo, see fixture).
_AIGW_SPEC_EXPRESSION = f"/claude?q={quote('$prompt', safe='$')}"


# ---------------------------------------------------------------------------
# Skip-gating
# ---------------------------------------------------------------------------


def _has_claude_code_keychain() -> bool:
    """Return True if Claude Code's keychain entry exists on this machine."""
    if not shutil.which("security"):
        return False
    user = os.environ.get("USER", "")
    if not user:
        return False
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                "Claude Code-credentials",
                "-a",
                user,
                "-w",
            ],
            capture_output=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _credentials_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or _has_claude_code_keychain()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_AIGATEWAY_DIR = (Path(__file__).resolve().parents[3] / "aigateway").resolve()


@pytest.fixture(scope="module")
def aigw_proxy(otlp_collector: OTLPCollector, httpbin_url: str):
    """SF server running claude-frontend + aigw-claude-backend + aigw-runner.

    The gateway subprocess is spawned by aigw-runner during SF startup.
    Teardown stops both processes.
    """
    if not _credentials_available():
        pytest.skip(
            "Neither ANTHROPIC_API_KEY env var nor a Claude Code keychain "
            "entry was found. The gateway needs one of these to authenticate "
            "the anthropic:default profile."
        )
    if not shutil.which("uv"):
        pytest.skip("`uv` not found in PATH; aigw-runner cannot spawn the gateway")
    if not _AIGATEWAY_DIR.exists():
        pytest.skip(f"apps/aigateway/ not found at {_AIGATEWAY_DIR}")

    internal_port = ServerManager.find_free_port()
    proxy_port = ServerManager.find_free_port()
    gateway_port = ServerManager.find_free_port()

    config = {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": internal_port,
            "ssl": False,
            "reload": False,
        },
        "plugins": [
            "tracing",
            "claude-frontend",
            "url4-specs",
            "url4-executor",
            "data-store",
            "aigw-base",
            "aigw-claude-backend",
            "aigw-runner",
        ],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
            "claude-frontend": {
                "active_spec": "aigw-prompt",
                "upstream_url": f"{httpbin_url}/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_port,
            },
            "url4-specs": {
                "specs": {
                    "aigw-prompt": {"expression": _AIGW_SPEC_EXPRESSION},
                },
            },
            "aigw-claude-backend": {
                "gateway_url": f"http://127.0.0.1:{gateway_port}",
                "auth_profile": "default",
                "default_model": "anthropic/claude-haiku-4-5",
                "timeout_seconds": 60,
            },
            "aigw-runner": {
                "port": gateway_port,
                "aigateway_dir": str(_AIGATEWAY_DIR),
                "startup_timeout_seconds": 10.0,
                "enabled": True,
            },
        },
    }

    mgr = ServerManager(config, session_id="e2e-aigw-claude")
    mgr.start(timeout=120)

    if not ServerManager.wait_for_port(proxy_port, timeout=60):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        pytest.fail(
            f"claude-frontend not listening on port {proxy_port}\n"
            f"Last server log lines:\n{last_logs}"
        )
    if not ServerManager.wait_for_port(gateway_port, timeout=60):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        pytest.fail(
            f"aigw-runner did not bring up gateway on port {gateway_port}\n"
            f"Last server log lines:\n{last_logs}"
        )

    # Confirm the gateway has an authenticated anthropic:default profile —
    # otherwise the chat call will return 404 profile_not_found.
    deadline = time.monotonic() + 15
    profile_state: str | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(
                f"http://127.0.0.1:{gateway_port}/v1/auth/profiles", timeout=3
            )
            if r.status_code == 200:
                for p in r.json().get("profiles", []):
                    if p.get("id") == "anthropic:default":
                        profile_state = p.get("state")
                        break
                if profile_state is not None:
                    break
        except httpx.RequestError:
            pass
        time.sleep(0.5)

    if profile_state != "authenticated":
        mgr.stop()
        pytest.skip(
            f"Gateway anthropic:default profile state is {profile_state!r}. "
            "Run `claude auth login` so the bootstrap can import credentials, "
            "or POST /v1/auth/anthropic/profiles to seed one manually."
        )

    yield mgr, proxy_port, gateway_port

    mgr.stop()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
def test_claude_frontend_to_aigw_to_anthropic(
    aigw_proxy: tuple[ServerManager, int, int],
    otlp_collector: OTLPCollector,
) -> None:
    """Round-trip a prompt through every layer; assert response + span chain."""
    _, proxy_port, gateway_port = aigw_proxy
    otlp_collector.clear()

    client = ClaudeCodeClient(proxy_url=f"http://127.0.0.1:{proxy_port}")
    resp = client.send_message(
        "Reply with the single English word: pong",
        timeout=90,
    )

    # ----------------------------- round-trip ------------------------------
    assert resp.status_code == 200, f"proxy responded {resp.status_code}: {resp.body}"

    mgr, _, _ = aigw_proxy
    user_text = resp.last_user_text
    # Diagnostic dump on failure — helps narrow which layer dropped the response.
    last_logs = "\n".join(mgr.logs.dump_last(50)) if mgr.logs else "<no logs>"
    debug = (
        f"\n--- raw resp.body ---\n{resp.body}"
        f"\n--- forwarded body (httpbin echo) ---\n{resp.echoed_body}"
        f"\n--- forwarded messages ---\n{resp.forwarded_messages}"
        f"\n--- last_user_text ---\n{user_text!r}"
        f"\n--- last 50 SF server log lines ---\n{last_logs}"
    )

    # Two acceptable outcomes:
    #  (a) Successful round-trip: the forwarded user message contains the
    #      gateway-substituted assistant reply.
    #  (b) Upstream Anthropic returned an error (e.g. 429 rate limit) — the
    #      chain still worked; we just got an error from the real provider.
    #      In that case claude-frontend surfaces an `sf_error_*` response
    #      body containing the layered error message — which proves the
    #      gateway and aigw-claude-backend were both invoked.
    body_id = resp.body.get("id", "")
    body_text = ""
    for part in resp.body.get("content", []):
        if isinstance(part, dict) and part.get("type") == "text":
            body_text += part.get("text", "")

    successful_substitution = len(user_text) > 5
    upstream_error_through_chain = (
        body_id.startswith("sf_error_")
        and "/claude" in body_text
        and ("aigw" in body_text.lower() or "rate" in body_text.lower() or "anthropic" in body_text.lower())
    )

    assert successful_substitution or upstream_error_through_chain, (
        f"Chain didn't reach the gateway, or response shape unexpected.{debug}"
    )

    # ------------------------------ span chain -----------------------------
    # Wait briefly for spans to flush through the OTLP collector.
    otlp_collector.wait_for_spans(3, timeout=15)
    span_names = {s.name for s in otlp_collector._spans}  # noqa: SLF001 — test-only

    # Each layer below MUST appear. If any is missing, someone has rerouted
    # the request and skipped a layer (e.g. mistakenly enabled the legacy
    # claude-backend-api alongside aigw-claude-backend).
    #
    # FastAPI's auto-instrumentation produces "<METHOD> <route_template>" spans
    # for every endpoint hit. We rely on those for layer evidence:
    #   POST /v1/messages          claude-frontend listener
    #   url4.*                     url4 executor (custom spans from url4-executor)
    #   GET /claude                aigw-claude-backend route on the SF server
    #   POST /v1/chat/completions  the gateway subprocess (also FastAPI)
    # Layers visible in the SF process's OTLP stream:
    #   POST /v1/messages          claude-frontend listener
    #   url4.*                     url4 executor (custom spans)
    #   GET /claude                aigw-claude-backend route handler
    expected_layers = {
        "claude_frontend": "POST /v1/messages",
        "url4_executor": "url4.evaluate",
        "aigw_backend_route": "GET /claude",
    }
    missing = {
        layer: span
        for layer, span in expected_layers.items()
        if not any(span in n for n in span_names)
    }
    assert not missing, (
        f"Missing spans for layers: {missing}\n"
        f"All spans: {sorted(span_names)}"
    )

    # The gateway subprocess emits its access log through the aigw_runner
    # daemon log thread, which forwards to the SF logger and ends up in
    # mgr.logs. Rather than instrument the child for OTLP (a separate
    # ticket), we look for the unmistakable access-log line that proves
    # the gateway saw the chat-completions POST during this test.
    all_logs = "\n".join(mgr.logs.dump_last(500)) if mgr.logs else ""
    assert "POST /v1/chat/completions" in all_logs, (
        "Gateway did not log a chat-completions POST during the test — "
        "the chain didn't reach the gateway subprocess.\n"
        f"Last log lines:\n{all_logs[-3000:]}"
    )

    # Final sanity probe: gateway is still healthy after the round-trip.
    health = httpx.get(f"http://127.0.0.1:{gateway_port}/healthz", timeout=3)
    assert health.status_code == 200
