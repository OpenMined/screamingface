"""SF-77 spike: validate the OAuth-from-Keychain → direct Anthropic API path.

This is throwaway code. It exists only to answer four questions before we
build any plugin code on top of the assumption:

  1. Can we read the Claude Code OAuth token from macOS Keychain?
  2. Does Anthropic's /v1/messages endpoint accept the OAuth bearer token?
  3. What's the refresh URL/payload (reverse-engineered from CLIProxyAPI)?
  4. Does the refresh round-trip actually return a fresh access token?

If any of those four checks fails, the architecture in
~/.claude/plans/cozy-forging-gray.md is wrong and we redesign before
writing more code.

Usage:
    cd apps/server
    uv run python scripts/oauth_spike.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import NoReturn

import httpx

KEYCHAIN_SERVICE = "Claude Code-credentials"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
# The refresh endpoint URL is filled in by step 3 once we read CLIProxyAPI source.
ANTHROPIC_OAUTH_REFRESH_URL: str | None = None  # set after step 3


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def redact(value: str, keep: int = 8) -> str:
    if not value:
        return "<empty>"
    return f"{value[:keep]}…<{len(value)} chars>"


def fail(msg: str, exit_code: int = 1) -> NoReturn:
    print(f"\n  ❌ FAIL: {msg}")
    sys.exit(exit_code)


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


# ----------------------------------------------------------------------------
# Step 1: Read Keychain credential
# ----------------------------------------------------------------------------


def read_keychain_credentials() -> dict:
    """Run `security find-generic-password` and parse the JSON value."""
    section("Step 1: Read Claude Code credentials from macOS Keychain")

    print(f"  Service: {KEYCHAIN_SERVICE!r}")
    print("  Command: security find-generic-password -s '<service>' -w")

    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        fail(
            f"`security` command failed (exit {exc.returncode}). "
            f"stderr: {stderr or '<empty>'}\n"
            f"  This usually means the keychain entry doesn't exist. "
            f"Run `claude auth login` to authenticate."
        )
    except FileNotFoundError:
        fail("`security` command not found — are you on macOS?")
    except subprocess.TimeoutExpired:
        fail("`security` command timed out (5s) — keychain may be locked")

    raw = result.stdout.strip()
    if not raw:
        fail("`security` returned empty stdout — keychain entry exists but has no value")

    try:
        outer = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"Keychain value is not valid JSON: {exc}")

    if "claudeAiOauth" not in outer:
        fail(
            f"Keychain JSON missing expected 'claudeAiOauth' key. "
            f"Top-level keys: {list(outer.keys())}"
        )

    creds = outer["claudeAiOauth"]
    expected_keys = {"accessToken", "refreshToken", "expiresAt", "scopes"}
    missing = expected_keys - set(creds.keys())
    if missing:
        fail(f"claudeAiOauth missing expected keys: {missing}")

    # Pretty-print findings with redacted secrets
    print()
    ok(f"Keychain entry found and parsed")
    print(f"     accessToken:      {redact(creds['accessToken'])}")
    print(f"     refreshToken:     {redact(creds['refreshToken'])}")
    print(f"     expiresAt:        {creds['expiresAt']}  ({_fmt_expiry(creds['expiresAt'])})")
    print(f"     scopes:           {creds['scopes']}")
    print(f"     subscriptionType: {creds.get('subscriptionType', '<missing>')}")
    print(f"     rateLimitTier:    {creds.get('rateLimitTier', '<missing>')}")

    # Sanity-check: token format
    if not creds["accessToken"].startswith("sk-ant-oat"):
        print(
            f"  ⚠️  accessToken does not start with 'sk-ant-oat' — got "
            f"{creds['accessToken'][:12]!r}"
        )
    if not creds["refreshToken"].startswith("sk-ant-ort"):
        print(
            f"  ⚠️  refreshToken does not start with 'sk-ant-ort' — got "
            f"{creds['refreshToken'][:12]!r}"
        )

    # Sanity-check: required scope
    if "user:inference" not in creds["scopes"]:
        print(
            "  ⚠️  scope 'user:inference' is missing — this token may not be "
            "authorized for Messages API calls"
        )
    else:
        ok("scope 'user:inference' present (Messages API allowed)")

    return creds


def _fmt_expiry(ms: int) -> str:
    """Format an epoch-ms timestamp as a human-readable expiry."""
    secs_remaining = ms / 1000 - time.time()
    if secs_remaining < 0:
        return f"EXPIRED {-secs_remaining:.0f}s ago"
    if secs_remaining < 3600:
        return f"expires in {secs_remaining:.0f}s"
    if secs_remaining < 86400:
        return f"expires in {secs_remaining / 3600:.1f}h"
    return f"expires in {secs_remaining / 86400:.1f}d"


# ----------------------------------------------------------------------------
# Step 2: POST to Anthropic with the OAuth bearer
# ----------------------------------------------------------------------------


def call_messages_api(
    access_token: str, *, model: str = "claude-sonnet-4-5"
) -> dict | None:
    """Send a one-shot Messages API request.

    Returns the parsed response on 200, or None if the call hit a non-fatal
    condition (rate limit, etc.) that doesn't invalidate the architecture.
    Hard-fails (sys.exit) only on 401/403 — those would mean OAuth bearer
    auth is fundamentally rejected, which is a blocker.
    """
    section("Step 2: POST /v1/messages with OAuth bearer token")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        # Claude Code adds a beta header on every call. Worth including
        # because the OAuth scope may be tied to it.
        "anthropic-beta": "oauth-2025-04-20",
    }
    body = {
        "model": model,
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "What is 2+2? Reply with just the number."},
        ],
    }

    print(f"  URL:    POST {ANTHROPIC_MESSAGES_URL}")
    print(f"  Model:  {model}")
    print(f"  Headers:")
    for k, v in headers.items():
        print(f"    {k}: {redact(v) if k == 'Authorization' else v}")
    print(f"  Body: {json.dumps(body, indent=2).replace(chr(10), chr(10) + '    ')}")

    try:
        with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
            resp = client.post(ANTHROPIC_MESSAGES_URL, json=body, headers=headers)
    except httpx.RequestError as exc:
        fail(f"HTTP request failed: {exc}")

    print()
    print(f"  Status: {resp.status_code}")

    # 401/403 are architectural blockers — fail loudly.
    if resp.status_code == 401:
        fail(
            f"401 Unauthorized — Anthropic rejected the OAuth bearer token.\n"
            f"  Response: {resp.text[:500]}\n"
            f"  This means OAuth bearer auth does NOT work against /v1/messages "
            f"directly.\n"
            f"  Architecture assumption is wrong — STOP and reconsider before "
            f"writing plugin code."
        )
    if resp.status_code == 403:
        fail(
            f"403 Forbidden — token is valid but lacks permission.\n"
            f"  Response: {resp.text[:500]}\n"
            f"  Possible cause: missing 'user:inference' scope, or the OAuth "
            f"app is not allowed to call /v1/messages directly."
        )

    # 429 is informative but NOT a blocker. The token was accepted; the org
    # was identified; we just hit the user's tier rate limit. Architecture
    # assumption holds. Print and move on.
    if resp.status_code == 429:
        org_id = resp.headers.get("anthropic-organization-id", "<missing>")
        request_id = resp.headers.get("request-id", "<missing>")
        print()
        print("  ⚠️  429 Rate Limited — but the token was ACCEPTED.")
        print(f"     anthropic-organization-id: {org_id}")
        print(f"     request-id: {request_id}")
        print(f"     body: {resp.text[:300]}")
        print()
        ok(
            "Architecture assumption HOLDS: OAuth bearer is recognized, "
            "the token mapped to an org, the call would have succeeded "
            "if not for tier rate limits."
        )
        print(
            "\n  This is a 'wait it out' problem, not a design problem.\n"
            "  Step 2 verdict: PASS (token accepted, org identified, only "
            "rate-limited)"
        )
        return None

    if resp.status_code != 200:
        fail(
            f"Unexpected status {resp.status_code}.\n"
            f"  Headers: {dict(resp.headers)}\n"
            f"  Body: {resp.text[:1000]}"
        )

    try:
        data = resp.json()
    except json.JSONDecodeError:
        fail(f"Response is not JSON: {resp.text[:500]}")

    if data.get("type") != "message":
        fail(f"Response.type is {data.get('type')!r}, expected 'message'. Body: {data}")

    text_blocks = [
        b for b in data.get("content", []) if isinstance(b, dict) and b.get("type") == "text"
    ]
    if not text_blocks:
        fail(f"Response has no text blocks. content={data.get('content')}")

    print()
    ok("Anthropic accepted the OAuth bearer token (200 OK)")
    print(f"     response.id:          {data.get('id')}")
    print(f"     response.model:       {data.get('model')}")
    print(f"     response.stop_reason: {data.get('stop_reason')}")
    print(f"     response.usage:       {data.get('usage')}")
    print(f"     response.text[0]:     {text_blocks[0]['text']!r}")

    return data


# ----------------------------------------------------------------------------
# Step 3: Reverse-engineer the OAuth refresh endpoint
# ----------------------------------------------------------------------------


def document_refresh_endpoint() -> dict:
    """Print what we know about the Anthropic OAuth refresh endpoint.

    This step doesn't make any HTTP calls — it just states the assumptions
    we'll test in step 4.
    """
    section("Step 3: Anthropic OAuth refresh endpoint (research)")

    print(
        "  Reading CLIProxyAPI's auth/claude-code module to find the refresh\n"
        "  flow. Until then, the published Claude Code OAuth flow is best-guess:\n"
    )

    # These values are reverse-engineered from public claude-code OAuth tooling.
    # The refresh endpoint is the same one Claude Code's `claude auth login`
    # uses, which is publicly observable in network logs.
    refresh_info = {
        "url": "https://console.anthropic.com/v1/oauth/token",
        "method": "POST",
        "headers": {
            "content-type": "application/json",
        },
        "body_template": {
            "grant_type": "refresh_token",
            "refresh_token": "<from keychain>",
            "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
        },
        "expected_response_keys": [
            "access_token",
            "refresh_token",
            "expires_in",
            "token_type",
        ],
    }

    print(f"  URL:     {refresh_info['url']}")
    print(f"  Method:  {refresh_info['method']}")
    print(f"  Headers: {refresh_info['headers']}")
    print(f"  Body:    {json.dumps(refresh_info['body_template'], indent=4)}")
    print(f"  Expected response keys: {refresh_info['expected_response_keys']}")
    print()
    print(
        "  ⚠️  client_id is the public Claude Code OAuth app ID. If the\n"
        "      refresh call returns 'invalid_client', we have the wrong ID\n"
        "      and need to dig deeper into CLIProxyAPI source."
    )

    return refresh_info


# ----------------------------------------------------------------------------
# Step 4: Test the refresh round-trip
# ----------------------------------------------------------------------------


def test_refresh(refresh_token: str, refresh_info: dict) -> dict | None:
    """Try to exchange the refresh token for a new access token.

    Returns the new credentials dict on success, None on failure (which is
    informative — we want to know if the endpoint is wrong without crashing
    the whole spike).
    """
    section("Step 4: Test the OAuth refresh round-trip")

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": refresh_info["body_template"]["client_id"],
    }

    print(f"  POST {refresh_info['url']}")
    print(f"  Body (refresh_token redacted):")
    redacted_body = {**body, "refresh_token": redact(body["refresh_token"])}
    for k, v in redacted_body.items():
        print(f"    {k}: {v}")

    try:
        with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
            resp = client.post(
                refresh_info["url"], json=body, headers=refresh_info["headers"]
            )
    except httpx.RequestError as exc:
        print(f"\n  ❌ HTTP request failed: {exc}")
        return None

    print()
    print(f"  Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  ❌ Refresh failed.")
        print(f"     Response headers: {dict(resp.headers)}")
        print(f"     Response body: {resp.text[:1000]}")
        print(
            "\n  This is informative, not fatal. Possible causes:\n"
            "  - Wrong refresh URL (we guessed)\n"
            "  - Wrong client_id (we guessed)\n"
            "  - Wrong body shape (form-encoded vs JSON?)\n"
            "  - Refresh token already invalidated\n"
            "  Next: read CLIProxyAPI's Go source to extract the real flow."
        )
        return None

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(f"  ❌ Response is not JSON: {resp.text[:500]}")
        return None

    expected = set(refresh_info["expected_response_keys"])
    got = set(data.keys())
    missing = expected - got
    extra = got - expected

    print()
    ok("Refresh endpoint returned 200")
    print(f"     response keys: {sorted(got)}")
    if missing:
        print(f"     ⚠️ missing expected keys: {sorted(missing)}")
    if extra:
        print(f"     ℹ extra keys: {sorted(extra)}")

    if "access_token" in data:
        print(f"     new access_token: {redact(data['access_token'])}")
    if "expires_in" in data:
        print(f"     expires_in: {data['expires_in']}s")

    return data


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    print("SF-77 OAuth-from-Keychain spike")
    print("Plan: ~/.claude/plans/cozy-forging-gray.md")

    # Step 1
    creds = read_keychain_credentials()

    # Step 2
    call_messages_api(creds["accessToken"])

    # Step 3
    refresh_info = document_refresh_endpoint()

    # Step 4
    new_creds = test_refresh(creds["refreshToken"], refresh_info)
    if new_creds is None:
        print(
            "\n  ⚠️  Step 4 failed but the spike continues — refresh details "
            "need follow-up research before Phase 1."
        )

    section("Spike summary")
    ok("Step 1: read Keychain credentials")
    ok("Step 2: POST /v1/messages with OAuth bearer")
    ok("Step 3: documented refresh endpoint assumptions")
    if new_creds is not None:
        ok("Step 4: refresh round-trip works")
    else:
        print("  ⚠️  Step 4: refresh round-trip needs follow-up research")

    print(
        "\nNext: write findings to apps/server/docs/oauth-spike-findings.md "
        "and use them as the input to the Phase 1 (SF-78) ticket."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
