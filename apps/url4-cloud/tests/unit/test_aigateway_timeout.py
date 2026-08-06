"""AI Gateway timeouts retain their transient failure contract."""

import httpx
import pytest

from url4.core.errors import ResolutionError
from url4.dag import run as url4_run
from url4_cloud.runner.config import ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world


@pytest.mark.asyncio
async def test_aigateway_timeout_maps_to_transient_resolution_error() -> None:
    model = "anthropic/claude-haiku-4-5"
    cfg = AigatewayConfig(
        models=(ModelSpec(id=model),),
        default_model=model,
        timeout_s=300.0,
    )

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(cfg, client=client)

        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(f"/{model}(ctx)!go", io=world.node)

    assert exc_info.value.code == "aigateway_timeout"
    assert exc_info.value.permanent is False
    assert str(exc_info.value) == (
        "aigateway did not respond within 300 seconds for model 'anthropic/claude-haiku-4-5'"
    )
