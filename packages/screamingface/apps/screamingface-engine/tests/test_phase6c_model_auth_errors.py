from __future__ import annotations

import httpx
import pytest
from url4 import Request, ResolutionError

from screamingface_engine.catalog import MODEL_ROUTES
from screamingface_engine.gateway import GatewayClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "connection_needs_reauth"), (403, "provider_access_denied")],
)
async def test_model_gateway_auth_failures_keep_stable_url4_codes(
    status: int,
    code: str,
) -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(lambda _request: httpx.Response(status)),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[0],
            Request("/codex/gpt-5.5", "question", "answer", {}),
        )
    await gateway.aclose()

    assert captured.value.code == code
    assert captured.value.permanent is True
