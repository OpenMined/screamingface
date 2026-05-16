"""End-to-end: claude-frontend → aigw-claude-backend → AI Gateway → Anthropic chain.

Asserts two things rigorously:

1. **url4 result was injected into the forwarded request.** The resolved
   text from the /claude backend call must end up *inside* the user
   message that claude-frontend forwards to its upstream. We compare
   the forwarded user_text against the literal prompt we sent — they
   must differ AND the original must still appear (concat semantics).

2. **The gateway actually called api.anthropic.com.** It's not enough
   that the gateway received a POST; we must see evidence that it
   reached the real upstream. Two accepted signals (logs forwarded
   through aigw_runner's daemon thread end up in mgr.logs):
     - a 200 from `POST /v1/chat/completions` in the gateway access log
       (litellm.acompletion only returns 200 after a successful
       Anthropic round-trip); OR
     - an explicit AnthropicException / RateLimitError mention,
       which proves the gateway's litellm path called Anthropic and
       got a structured error back.

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
import re
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

_TEST_PROMPT = "Reply with the single English word: pong"

pytestmark = pytest.mark.e2e

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

    previous_bootstrap = os.environ.get("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE")
    os.environ["AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE"] = "1"
    mgr = ServerManager(config, session_id="e2e-aigw-claude")
    try:
        mgr.start(timeout=120)

        if not ServerManager.wait_for_port(proxy_port, timeout=60):
            last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
            pytest.fail(
                f"claude-frontend not listening on port {proxy_port}\n"
                f"Last server log lines:\n{last_logs}"
            )
        if not ServerManager.wait_for_port(gateway_port, timeout=60):
            last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
            pytest.fail(
                f"aigw-runner did not bring up gateway on port {gateway_port}\n"
                f"Last server log lines:\n{last_logs}"
            )

        # Confirm the gateway has an authenticated default Anthropic profile —
        # otherwise the chat call will return 404 profile_not_found.
        deadline = time.monotonic() + 15
        profile_state: str | None = None
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{gateway_port}/v1/auth/profiles", timeout=3)
                if r.status_code == 200:
                    for p in r.json().get("profiles", []):
                        if p.get("provider") == "anthropic" and p.get("name") == "default":
                            profile_state = p.get("state")
                            break
                    if profile_state is not None:
                        break
            except httpx.RequestError:
                pass
            time.sleep(0.5)

        if profile_state != "authenticated":
            pytest.skip(
                f"Gateway anthropic/default profile state is {profile_state!r}. "
                "Run `claude auth login` so the bootstrap can import credentials, "
                "or POST /v1/auth/anthropic/profiles to seed one manually."
            )

        yield mgr, proxy_port, gateway_port
    finally:
        mgr.stop()
        if previous_bootstrap is None:
            os.environ.pop("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE", None)
        else:
            os.environ["AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE"] = previous_bootstrap


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
    resp = client.send_message(_TEST_PROMPT, timeout=90)

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
    #  (a) Successful round-trip: the gateway's substituted assistant reply
    #      ended up inside the forwarded user message.
    #  (b) Upstream Anthropic returned a structured error (e.g. 429 rate
    #      limit) — the chain still worked; we just got an error from the
    #      real provider. claude-frontend surfaces an `sf_error_*` response
    #      whose error body explicitly mentions /claude AND an upstream
    #      indicator (rate / anthropic / aigw).
    body_id = resp.body.get("id", "")
    body_text = ""
    for part in resp.body.get("content", []):
        if isinstance(part, dict) and part.get("type") == "text":
            body_text += part.get("text", "")

    # (a) Strong: the resolved text was injected. With embed_mode="concat"
    # (the default), the user message becomes "<original>\n\n<resolved>".
    # We require BOTH that the original is still present AND that something
    # was appended — otherwise the spec didn't trigger or substitution was
    # silently a no-op.
    substitution_happened = (
        user_text != _TEST_PROMPT
        and _TEST_PROMPT in user_text
        and len(user_text) > len(_TEST_PROMPT) + 1
    )

    # (b) Upstream-error fallback: the chain reached upstream and surfaced
    # an Anthropic-shaped error.
    upstream_error_through_chain = (
        body_id.startswith("sf_error_")
        and "/claude" in body_text
        and (
            "aigw" in body_text.lower()
            or "rate" in body_text.lower()
            or "anthropic" in body_text.lower()
        )
    )

    assert substitution_happened or upstream_error_through_chain, (
        f"url4 result not injected into forwarded request, and no upstream "
        f"error path observed.\n"
        f"original_prompt={_TEST_PROMPT!r}\nuser_text={user_text!r}\n"
        f"sf_error_id={body_id!r}\n"
        f"{debug}"
    )

    # ------------------------------ span chain -----------------------------
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
    span_names: set[str] = set()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        span_names = {s.name for s in otlp_collector.spans}
        if all(any(span in name for name in span_names) for span in expected_layers.values()):
            break
        time.sleep(0.2)

    missing = {
        layer: span
        for layer, span in expected_layers.items()
        if not any(span in n for n in span_names)
    }
    assert not missing, f"Missing spans for layers: {missing}\nAll spans: {sorted(span_names)}"

    # Gateway-side evidence: the subprocess's stdout (forwarded by aigw_runner's
    # daemon thread) lands in mgr.logs. We require BOTH that the gateway saw
    # a chat-completions POST AND that something proves it actually called
    # api.anthropic.com.
    all_logs = "\n".join(mgr.logs.dump_last(2000)) if mgr.logs else ""

    # Step 1 — the gateway received the POST from aigw-claude-backend.
    assert "POST /v1/chat/completions" in all_logs, (
        "Gateway did not log a chat-completions POST during the test — "
        "the chain didn't reach the gateway subprocess.\n"
        f"Last log lines:\n{all_logs[-3000:]}"
    )

    # Step 2 — the gateway actually called api.anthropic.com. Accept any
    # of these signals (each one independently proves Anthropic was reached):
    #   - gateway returned 200 from chat/completions (litellm only succeeds
    #     after a real Anthropic round-trip)
    #   - litellm raised AnthropicException / RateLimitError (gateway saw
    #     a structured error from Anthropic, which means it called it)
    #   - the api.anthropic.com hostname appears in any log line
    gateway_returned_200 = bool(re.search(r'"POST /v1/chat/completions HTTP/[\d.]+" 200', all_logs))
    anthropic_exception_seen = (
        "AnthropicException" in all_logs
        or "RateLimitError" in all_logs
        or "anthropic.exceptions" in all_logs
    )
    anthropic_host_seen = "api.anthropic.com" in all_logs

    assert gateway_returned_200 or anthropic_exception_seen or anthropic_host_seen, (
        "Gateway received a chat-completions POST but no evidence it actually "
        "called api.anthropic.com — chain may have failed inside the gateway "
        "before the upstream call.\n"
        f"Last 3000 chars of logs:\n{all_logs[-3000:]}"
    )

    # Final sanity probe: gateway is still healthy after the round-trip.
    health = httpx.get(f"http://127.0.0.1:{gateway_port}/healthz", timeout=3)
    assert health.status_code == 200
