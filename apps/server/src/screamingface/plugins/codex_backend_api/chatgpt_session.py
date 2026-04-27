"""ChatGPT-backend session helpers (curl_cffi + Cloudflare bypass).

The chatgpt.com/backend-api endpoint requires browser-fingerprint TLS
to bypass Cloudflare. We use ``curl_cffi`` with the
``chrome99_android`` profile. ``curl_cffi`` is sync-only, so callers
should invoke :func:`post_responses` from an async context via
``run_in_executor``.

Header building, body framing, and the curl_cffi POST live here so the
main backend class stays focused on dispatch + error mapping.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart

CHATGPT_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
CURL_CFFI_PROFILE = "chrome99_android"
CHATGPT_CLIENT_VERSION = "0.120.0"

_DEFAULT_INSTRUCTIONS = (
    "You are a helpful assistant. Answer the user's question based only on "
    "the provided context. Be concise and factual."
)


def build_chatgpt_headers(auth_headers: dict[str, str], account_id: str) -> dict[str, str]:
    """Layer the chatgpt.com session headers on top of an Authorization header."""
    session_id = str(uuid.uuid4())
    headers = dict(auth_headers)
    headers.update(
        {
            "chatgpt-account-id": account_id,
            "originator": "codex_exec",
            "session_id": session_id,
            "version": CHATGPT_CLIENT_VERSION,
            "x-client-request-id": session_id,
            "x-codex-window-id": f"{session_id}:0",
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
    )
    return headers


def build_responses_body(
    messages: Iterable[CoreMessage],
    *,
    model: str,
    system: str | None = None,
) -> dict:
    """Build the ``/codex/responses`` POST body from canonical messages.

    Only text parts are forwarded; chatgpt.com requires a non-empty
    ``instructions`` field, so a short default is used when no
    ``system`` is given.
    """
    prompt_parts: list[str] = []
    for msg in messages:
        if isinstance(msg.content, str):
            prompt_parts.append(msg.content)
            continue
        for part in msg.content:
            if isinstance(part, TextPart):
                prompt_parts.append(part.text)

    return {
        "model": model,
        "instructions": system or _DEFAULT_INSTRUCTIONS,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": t}],
            }
            for t in prompt_parts
        ],
        "store": False,
        "stream": True,
        "reasoning": {"effort": "high"},
        "text": {"verbosity": "low"},
        "client_metadata": {"x-codex-installation-id": str(uuid.uuid4())},
    }


def build_health_probe_body() -> dict:
    """Tiny body used by the health endpoint to check auth + connectivity."""
    return {
        "model": "gpt-5.4",
        "instructions": "Say OK.",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
        "store": False,
        "stream": True,
        "reasoning": {"effort": "high"},
        "text": {"verbosity": "low"},
    }


def post_responses_sync(
    body: dict,
    headers: dict[str, str],
    *,
    timeout: float = 300.0,
    url: str = CHATGPT_RESPONSES_URL,
) -> tuple[int, str, dict]:
    """POST to chatgpt.com via curl_cffi (sync). Returns (status, text, headers)."""
    from curl_cffi.requests import Session

    with Session(impersonate=CURL_CFFI_PROFILE) as s:
        r = s.post(url, json=body, headers=headers, timeout=timeout)
        return r.status_code, r.text, dict(r.headers)


async def auth_headers_for(auth: CodexOAuth) -> tuple[dict[str, str], str]:
    """Bundle OAuth header + account id retrieval used by both run() and health()."""
    headers = await auth.get_authorization_header()
    return headers, auth.get_account_id()
