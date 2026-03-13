"""E2E tests for DNS override with real /etc/hosts modification.

These tests require root (sudo) because they modify /etc/hosts.
Run with: sudo uv run pytest tests/test_intercept_e2e.py -v
"""

from __future__ import annotations

import asyncio
import os
import socket

import httpx
import pytest

# Skip entire module if not running as root
pytestmark = pytest.mark.skipif(os.getuid() != 0, reason="requires root")

DOMAIN = "api.anthropic.com"


@pytest.fixture
def real_ip() -> str:
    """Capture the real IP before any /etc/hosts modification."""
    addrs = socket.getaddrinfo(DOMAIN, 443, socket.AF_INET)
    return str(addrs[0][4][0])


@pytest.fixture
def hosts_patched(real_ip: str):
    """Add /etc/hosts entry pointing DOMAIN → 127.0.0.1, restore on teardown."""
    from screamingface.plugins.claude_intercept.hosts import (
        add_entries,
        flush_dns,
        has_entries,
        remove_entries,
    )

    # Safety: don't double-patch
    if has_entries():
        pytest.skip("hosts already patched (stale state from previous run?)")

    add_entries([DOMAIN], "127.0.0.1")
    flush_dns()
    yield real_ip
    remove_entries()
    flush_dns()


@pytest.fixture
def dns_patched(hosts_patched: str):
    """Install the DNS monkey-patch with the real IP."""
    from screamingface.plugins.claude_intercept import dns

    dns.install({DOMAIN: hosts_patched})
    yield hosts_patched
    dns.uninstall()


class TestDNSOverrideE2E:
    """Verify DNS monkey-patch works end-to-end with real /etc/hosts."""

    def test_hosts_redirects_to_localhost(self, hosts_patched: str) -> None:
        """After /etc/hosts mod, raw getaddrinfo returns 127.0.0.1."""
        addrs = socket.getaddrinfo(DOMAIN, 443, socket.AF_INET)
        ip = str(addrs[0][4][0])
        assert ip == "127.0.0.1", f"Expected 127.0.0.1, got {ip}"

    def test_dns_patch_overrides_to_real_ip(self, dns_patched: str) -> None:
        """With DNS patch installed, getaddrinfo returns the real IP."""
        real_ip = dns_patched
        addrs = socket.getaddrinfo(DOMAIN, 443, socket.AF_INET)
        ip = str(addrs[0][4][0])
        assert ip == real_ip, f"Expected {real_ip}, got {ip}"

    def test_dns_patch_handles_bytes_hostname(self, dns_patched: str) -> None:
        """DNS patch handles bytes hostnames (httpx passes bytes)."""
        real_ip = dns_patched
        addrs = socket.getaddrinfo(DOMAIN.encode("ascii"), 443, socket.AF_INET)
        ip = str(addrs[0][4][0])
        assert ip == real_ip, f"Expected {real_ip}, got {ip}"

    def test_asyncio_loop_getaddrinfo_uses_patch(self, dns_patched: str) -> None:
        """Standard asyncio loop.getaddrinfo() goes through the monkey-patch."""
        real_ip = dns_patched

        async def resolve():
            loop = asyncio.get_event_loop()
            addrs = await loop.getaddrinfo(DOMAIN, 443, family=socket.AF_INET)
            return str(addrs[0][4][0])

        ip = asyncio.run(resolve())
        assert ip == real_ip, f"Expected {real_ip}, got {ip}"

    def test_uvloop_getaddrinfo_bypasses_patch(self, dns_patched: str) -> None:
        """uvloop's getaddrinfo bypasses the monkey-patch (known limitation)."""
        try:
            import uvloop
        except ImportError:
            pytest.skip("uvloop not installed")

        async def resolve():
            loop = asyncio.get_event_loop()
            addrs = await loop.getaddrinfo(DOMAIN, 443, family=socket.AF_INET)
            return str(addrs[0][4][0])

        ip = uvloop.run(resolve())
        # uvloop resolves via libuv C code, sees /etc/hosts → 127.0.0.1
        assert ip == "127.0.0.1", (
            f"Expected uvloop to bypass patch and return 127.0.0.1, got {ip}"
        )

    def test_httpx_reaches_real_api(self, dns_patched: str) -> None:
        """httpx request to DOMAIN goes to the real API, not localhost."""
        import certifi
        import ssl

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

        async def make_request():
            async with httpx.AsyncClient(verify=ssl_ctx) as client:
                # No API key → expect 401, but proves we reached the real server
                resp = await client.post(
                    f"https://{DOMAIN}/v1/messages",
                    json={"model": "test", "max_tokens": 1, "messages": []},
                    headers={"anthropic-version": "2023-06-01"},
                )
                return resp.status_code

        status = asyncio.run(make_request())
        # 401 = reached real Anthropic API (auth rejected)
        # If we got SSL error or connection refused, the patch didn't work
        assert status == 401, f"Expected 401 from real API, got {status}"
