"""A proxy in front of aigateway must fail diagnosably, not as a JSONDecodeError.

FEATURE: ``AIGATEWAY_BASE_URL`` can point at anything an operator configures. When something
sits in front of aigateway and intercepts the request — an access gateway, an auth proxy, a
mesh — the Runner gets that proxy's **redirect to a login page**, not aigateway's JSON.

INVARIANT: ``_raise_for_status`` treats any 3xx as a permanent :class:`ResolutionError`. It
previously returned early for every status below 400, so a 302's HTML body reached
``resp.json()`` and surfaced as a bare ``json.decoder.JSONDecodeError`` with no indication that
a proxy was involved. Observed live: a Cloudflare-Access-fronted aigateway answered
``GET /v1/models`` with a 302 login page (httpx does not follow redirects here).
"""

import httpx
import pytest
from url4.core.errors import ResolutionError

from url4_cloud_runner.aigateway_connector import AigatewayConfig, build_aigateway_world

_TOKEN = "tok"  # noqa: S105 - not a real credential


def _redirect_handler(request: httpx.Request) -> httpx.Response:
    # What Cloudflare Access actually returns: a 302 to its login page, with an HTML body.
    return httpx.Response(
        302,
        headers={"location": "https://team.cloudflareaccess.com/cdn-cgi/access/login/x"},
        text="<html><head><title>302 Found</title></head><body></body></html>",
    )


def _html_200_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="<html>not json</html>", headers={"content-type": "text/html"})


@pytest.mark.asyncio
async def test_a_redirect_from_a_fronting_proxy_raises_a_named_error() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_redirect_handler), base_url="http://aigw"
    )

    with pytest.raises(ResolutionError) as exc_info:
        await build_aigateway_world(AigatewayConfig(), token=_TOKEN, client=client)

    # INVARIANT: a named, permanent error — never a JSONDecodeError escaping to the Job log.
    assert exc_info.value.code == "aigateway_bad_response"
    assert exc_info.value.permanent is True
    assert "302" in str(exc_info.value)


@pytest.mark.asyncio
async def test_a_non_json_success_body_raises_a_named_error() -> None:
    # WHY also guard 200: a transparent proxy can answer 200 with an HTML error/interstitial,
    # which `_raise_for_status` legitimately lets through — the JSON decode must still be safe.
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_html_200_handler), base_url="http://aigw"
    )

    with pytest.raises(ResolutionError) as exc_info:
        await build_aigateway_world(AigatewayConfig(), token=_TOKEN, client=client)

    assert exc_info.value.code == "aigateway_bad_response"
    assert exc_info.value.permanent is True
