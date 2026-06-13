"""GeminiBackend — dual-path backend for Google Gemini models.

OAuth path (oauth-personal):
  → cloudcode-pa.googleapis.com/v1internal (Code Assist API)
  → Requires loadCodeAssist setup, request envelope wrapping

API key path (GOOGLE_API_KEY / GEMINI_API_KEY):
  → generativelanguage.googleapis.com/v1beta (standard public API)
  → Standard GenerateContent request format
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid

import certifi
import httpx

from screamingface.plugins.gemini_backend_api.adapter import GeminiAdapter
from screamingface.plugins.gemini_backend_api.auth import GeminiAuth
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

logger = logging.getLogger(__name__)

# Standard public API (API-key auth only)
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Code Assist API (OAuth auth)
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"

MAX_429_RETRIES = 3

# Cap on cumulative 429-retry sleep within a single request. The
# request-level test timeout is 45s; if we obey provider retry-after
# headers without a cap, multiple long delays stack and surface as
# httpx.ReadTimeout instead of a clean BackendError(429). Stop early
# once the next sleep would exceed this budget.
MAX_TOTAL_429_WAIT_SECONDS = 30.0


class GeminiBackend(Backend):
    def __init__(
        self,
        *,
        auth: GeminiAuth | None = None,
        adapter: GeminiAdapter | None = None,
        http_client_factory=None,
        fallback_models: list[str] | None = None,
        max_total_wait_seconds: float = MAX_TOTAL_429_WAIT_SECONDS,
        aigw_source: AigwTokenSource | None = None,
    ) -> None:
        self._auth = auth or GeminiAuth(aigw_source=aigw_source)
        self._adapter = adapter or GeminiAdapter()
        self._http_factory = http_client_factory or self._default_http_factory
        # Code Assist session state (OAuth path only)
        self._project_id: str | None = None
        self._session_id: str = str(uuid.uuid4())
        self._setup_lock = asyncio.Lock()
        # 429 cascade fallback chain — when the configured model returns
        # quota-exhausted 429s, try the next model in this list before
        # giving up. Each model has its own quota bucket on Code Assist.
        # Empty list = no fallback (legacy behavior).
        self._fallback_models = fallback_models or []
        self._max_total_wait_seconds = max_total_wait_seconds

    @staticmethod
    def _default_http_factory():
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            verify=ssl_ctx,
        )

    def _code_assist_base_url(self) -> str:
        return f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}"

    async def _ensure_setup(self) -> None:
        """Call loadCodeAssist to get projectId (OAuth path only)."""
        if self._project_id is not None:
            return
        async with self._setup_lock:
            if self._project_id is not None:
                return
            headers = await self._auth.get_authorization_header()
            headers["content-type"] = "application/json"
            url = f"{self._code_assist_base_url()}:loadCodeAssist"
            body = {
                "metadata": {
                    "ideType": "IDE_UNSPECIFIED",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                },
            }
            try:
                async with self._http_factory() as client:
                    resp = await client.post(url, json=body, headers=headers)
            except httpx.RequestError as exc:
                raise BackendError(
                    f"Code Assist API unreachable during setup: {exc}", status=None
                ) from exc

            if resp.status_code != 200:
                raise BackendError(
                    f"loadCodeAssist failed ({resp.status_code}): {resp.text[:500]}",
                    status=resp.status_code,
                )

            data = resp.json()
            self._project_id = data.get("cloudaicompanionProject")
            tier_name = data.get("currentTier", {}).get("name", "unknown")
            logger.info(
                "gemini-backend-api: Code Assist session ready, project=%s, tier=%s",
                self._project_id,
                tier_name,
            )

    def _wrap_code_assist_request(self, model: str, inner_body: dict) -> dict:
        """Wrap a standard GenerateContent body in the Code Assist envelope."""
        return {
            "model": model,
            "project": self._project_id,
            "user_prompt_id": str(uuid.uuid4()),
            "request": {
                **inner_body,
                "session_id": self._session_id,
            },
        }

    @staticmethod
    def _unwrap_code_assist_response(data: dict) -> dict:
        """Unwrap Code Assist response envelope → standard GenerateContent response."""
        if "response" in data:
            return data["response"]
        return data

    async def health(self, model: str = "gemini-2.5-flash") -> HealthStatus:
        """Check auth validity.

        For OAuth: calls loadCodeAssist (no rate-limited generation needed).
        For API key: makes a minimal generateContent call.
        """
        if self._auth.is_api_key_auth():
            return await self._health_api_key(model)
        return await self._health_oauth(model)

    async def _health_oauth(self, model: str = "gemini-2.5-flash") -> HealthStatus:
        """OAuth health probe: loadCodeAssist + minimal generateContent.

        ``loadCodeAssist`` alone isn't quota-metered, so a bare call to it
        can't detect ``generateContent`` 429s. We do a 1-token
        ``generateContent`` probe afterwards so the health response
        surfaces rate-limit state (and downstream tests can skip
        cleanly instead of timing out on retries).
        """
        try:
            await self._ensure_setup()
        except BackendError as exc:
            if exc.status in (401, 403):
                return HealthStatus(authenticated=False, error=str(exc))
            return HealthStatus(authenticated=True, error=str(exc))
        except AuthError as exc:
            return HealthStatus(authenticated=False, error=str(exc))
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        # Minimal generateContent probe — same pattern as _health_api_key.
        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))
        headers["content-type"] = "application/json"

        probe_body = self._wrap_code_assist_request(
            model,
            {
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            },
        )
        url = f"{self._code_assist_base_url()}:generateContent"
        try:
            async with self._http_factory() as client:
                resp = await client.post(url, json=probe_body, headers=headers)
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        if resp.status_code == 200:
            return HealthStatus(authenticated=True)
        if resp.status_code == 429:
            return HealthStatus(authenticated=True, error="rate limited")
        if resp.status_code in (401, 403):
            return HealthStatus(
                authenticated=False,
                error=f"API rejected credentials (HTTP {resp.status_code}): {resp.text[:300]}",
            )
        return HealthStatus(
            authenticated=True,
            error=f"Unexpected API status {resp.status_code}: {resp.text[:300]}",
        )

    async def _health_api_key(self, model: str) -> HealthStatus:
        try:
            headers = await self._auth.get_authorization_header()
        except Exception as exc:
            return HealthStatus(authenticated=False, error=str(exc))

        headers["content-type"] = "application/json"
        body = {
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        }
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        try:
            async with self._http_factory() as client:
                resp = await client.post(url, json=body, headers=headers)
        except Exception as exc:
            return HealthStatus(authenticated=True, error=f"API unreachable: {exc}")

        if resp.status_code == 200:
            return HealthStatus(authenticated=True)
        if resp.status_code == 429:
            return HealthStatus(authenticated=True, error="rate limited")
        if resp.status_code in (401, 403):
            return HealthStatus(
                authenticated=False,
                error=f"API rejected credentials (HTTP {resp.status_code}): {resp.text[:300]}",
            )
        return HealthStatus(
            authenticated=True,
            error=f"Unexpected API status {resp.status_code}: {resp.text[:300]}",
        )

    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 16000,
        temperature: float | None = None,
        timeout_seconds: float = 300.0,
    ) -> CoreMessage:
        body = self._adapter.to_provider_format(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        api_model = body.pop("_model", model)
        is_api_key = self._auth.is_api_key_auth()

        # Build the model-attempt chain: the configured model first, then
        # any fallback models (deduplicated, preserving order). When the
        # configured model returns 429 QUOTA_EXHAUSTED, the next entry's
        # quota bucket may still be intact.
        chain: list[str] = [api_model]
        for fb in self._fallback_models:
            if fb not in chain:
                chain.append(fb)

        last_429: BackendError | None = None
        for attempt_model in chain:
            try:
                if is_api_key:
                    response_data = await self._run_api_key(body, attempt_model)
                else:
                    response_data = await self._run_oauth(body, attempt_model)
                if attempt_model != api_model:
                    logger.warning(
                        "gemini-backend-api: %s 429-exhausted, served from fallback %s",
                        api_model,
                        attempt_model,
                    )
                return self._adapter.from_provider_response(response_data)
            except BackendError as exc:
                if exc.status != 429:
                    raise
                last_429 = exc
                logger.info(
                    "gemini-backend-api: 429 on %s, trying next model in chain",
                    attempt_model,
                )
                continue

        # Whole chain exhausted; surface the last 429.
        assert last_429 is not None
        raise last_429

    async def _run_api_key(self, body: dict, model: str) -> dict:
        """Standard path: generativelanguage.googleapis.com with API key."""
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
        return await self._post_with_retry(body, url)

    async def _run_oauth(self, body: dict, model: str) -> dict:
        """Code Assist path: cloudcode-pa.googleapis.com with OAuth."""
        await self._ensure_setup()
        wrapped = self._wrap_code_assist_request(model, body)
        url = f"{self._code_assist_base_url()}:generateContent"
        raw = await self._post_with_retry(wrapped, url)
        return self._unwrap_code_assist_response(raw)

    async def _post_with_retry(self, body: dict, url: str) -> dict:
        headers = await self._auth.get_authorization_header()
        headers["content-type"] = "application/json"
        total_waited = 0.0

        for attempt in range(MAX_429_RETRIES + 1):
            resp = await self._do_post(body, headers, url)

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise BackendError(
                        f"Gemini returned 200 but body is not JSON: {exc}",
                        status=200,
                    ) from exc

            if resp.status_code == 401:
                if attempt == 0:
                    logger.warning("gemini-backend-api: 401, refreshing token and retrying")
                    self._auth.invalidate_cache()
                    headers = await self._auth.get_authorization_header()
                    headers["content-type"] = "application/json"
                    continue
                raise AuthError(
                    "Authentication failed twice against Gemini API. "
                    "Run 'gemini' in your terminal to re-authenticate."
                )

            if resp.status_code == 429:
                retry_delay = self._parse_retry_delay(resp)
                if attempt < MAX_429_RETRIES and retry_delay is not None:
                    wait = retry_delay + 0.5
                    if total_waited + wait > self._max_total_wait_seconds:
                        logger.warning(
                            "gemini-backend-api: 429 retry-after %.1fs would exceed "
                            "max_total_wait %.1fs (already waited %.1fs); raising",
                            wait,
                            self._max_total_wait_seconds,
                            total_waited,
                        )
                        raise BackendError(
                            f"Gemini rate limit exceeded (429); cumulative retry "
                            f"wait would exceed {self._max_total_wait_seconds:.0f}s "
                            f"budget (next retry-after={wait:.1f}s, "
                            f"already waited={total_waited:.1f}s).",
                            status=429,
                            retry_after=retry_delay,
                        )
                    logger.info(
                        "gemini-backend-api: 429, retrying in %.1fs (attempt %d/%d)",
                        wait,
                        attempt + 1,
                        MAX_429_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    total_waited += wait
                    continue
                raise BackendError(
                    "Gemini rate limit exceeded (429).",
                    status=429,
                    retry_after=retry_delay,
                )

            if resp.status_code == 403:
                raise AuthError(f"Gemini returned 403 Forbidden: {resp.text[:500]}")

            raise BackendError(
                f"Gemini API error {resp.status_code}: {resp.text[:500]}",
                status=resp.status_code,
            )

        # Should not reach here, but just in case
        raise BackendError("Gemini API: max retries exceeded", status=429)

    @staticmethod
    def _parse_retry_delay(resp: httpx.Response) -> float | None:
        """Extract retry delay from 429 response (Code Assist or standard)."""
        # Try Code Assist format: error.details[].retryDelay
        try:
            data = resp.json()
            detail = data if "error" in data else json.loads(data.get("detail", "{}"))
            for d in detail.get("error", {}).get("details", []):
                if "retryDelay" in d:
                    return float(d["retryDelay"].rstrip("s"))
        except Exception:
            pass
        # Try standard retry-after header
        raw = resp.headers.get("retry-after")
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    async def _do_post(self, body: dict, headers: dict[str, str], url: str) -> httpx.Response:
        from screamingface.plugins.llm_base._tracing import (
            set_provider_attrs,
            traced_provider_post,
        )

        with traced_provider_post("gemini", url):
            try:
                async with self._http_factory() as client:
                    resp = await client.post(url, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise BackendError(f"Gemini request timed out: {exc}", status=None) from exc
            except httpx.RequestError as exc:
                raise BackendError(f"Gemini request failed: {exc}", status=None) from exc
            set_provider_attrs(
                {
                    "http.status_code": resp.status_code,
                    "http.response.size": len(resp.content),
                    "gen_ai.request.model": body.get("model"),
                }
            )
            return resp
