from __future__ import annotations

import base64
import json

import httpx
import pytest

from aigateway.plugins.anthropic_provider.plugin import AnthropicProviderPlugin
from aigateway.plugins.codex_provider.plugin import CodexProviderPlugin
from aigateway.plugins.gemini_provider.plugin import GeminiProviderPlugin


def _jwt(payload: dict) -> str:
    def encode(value: dict | bytes) -> str:
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.{encode(b'sig')}"


@pytest.mark.asyncio
async def test_codex_extracts_identity_from_id_token() -> None:
    identity = await CodexProviderPlugin().extract_identity(
        {"id_token": _jwt({"sub": "sub-1", "email": "codex@example.com", "name": "Codex User"})}
    )

    assert identity is not None
    assert identity.sub == "sub-1"
    assert identity.email == "codex@example.com"
    assert identity.name == "Codex User"


@pytest.mark.asyncio
async def test_gemini_extracts_identity_from_userinfo_when_id_token_missing() -> None:
    def factory() -> httpx.AsyncClient:
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(
                200,
                json={"sub": "google-sub", "email": "gemini@example.com", "name": "Gemini User"},
            )
        )
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    identity = await GeminiProviderPlugin().extract_identity(
        {"access_token": "access-token"},
        http_client_factory=factory,
    )

    assert identity is not None
    assert identity.sub == "google-sub"
    assert identity.email == "gemini@example.com"
    assert identity.name == "Gemini User"


@pytest.mark.asyncio
async def test_anthropic_returns_no_synthetic_identity() -> None:
    identity = await AnthropicProviderPlugin().extract_identity(
        {"access_token": "tok", "refresh_token": "refresh"}
    )

    assert identity is None
