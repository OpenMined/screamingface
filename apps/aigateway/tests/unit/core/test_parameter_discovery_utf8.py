"""Discovery snapshots reject byte sequences that are not valid UTF-8."""

from __future__ import annotations

import httpx
import pytest

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    HttpxDiscoveryClient,
    fetch_discovery_json,
)


@pytest.mark.asyncio
async def test_invalid_utf8_is_a_sanitized_malformed_json_failure() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"unsupported_model":"model-\xffname"}',
        )

    client = HttpxDiscoveryClient(transport=httpx.MockTransport(respond))

    with pytest.raises(DiscoveryError) as captured:
        await fetch_discovery_json(
            "https://catalog.example/models",
            allowed_origins=frozenset({"https://catalog.example"}),
            client=client,
        )

    assert captured.value.reason == "malformed_json"
    assert captured.value.__cause__ is None
