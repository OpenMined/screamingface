# Frontend Terminal-Ensemble Reframing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the four CLI frontends (claude, codex, gemini, ollama) so their inference routes terminate at an in-process url4/ensemble resolution and synthesize provider-native responses instead of proxying to real upstreams.

**Architecture:** Each frontend's inference leg (and only that leg) stops forwarding to the real provider; it resolves the active url4 spec (`$prompt` dynamic or static) and synthesizes the provider's native unary/streaming envelope using a single shared `terminal_response.py` module. The `$prompt` blob is the FULL serialized transcript (conversation-aware), responses echo a deterministic id plus plausible non-zero usage, and resolution errors render as a normal completed/200 envelope whose assistant text is the visible `[url4 error] ...+traceback`. Non-inference routes keep real-upstream passthrough unchanged; the cutover is direct with no feature flag.

**Tech Stack:** Python 3.12, FastAPI, pytest, ruff 0.9.0, pyright; apps/server.

Spec: [`docs/superpowers/plans/2026-06-04-frontend-terminal-ensemble-spec.md`](docs/superpowers/plans/2026-06-04-frontend-terminal-ensemble-spec.md)

---

## Settled gating decisions (authoritative)

These govern every task below; where a milestone's original draft conflicts, the decision here wins.

- **A. CONVERSATION-AWARE.** The `$prompt` blob is the FULL serialized transcript (not just the last user turn). Each frontend replaces `_extract_last_user_text` with `_extract_turns(body) -> list[tuple[str, str]]` then calls the shared `serialize_transcript(turns) -> str` to build the blob. Responses echo a DETERMINISTIC id (`deterministic_id(...)`) and PLAUSIBLE non-zero usage (estimated from transcript + result length via `estimate_tokens`). Static specs still ignore the CLI prompt entirely; conversation-aware only governs the `$prompt` path.
- **B. KEEP REAL-UPSTREAM PASSTHROUGH.** Only the INFERENCE route becomes terminal/synthetic. Non-inference routes still FORWARD to the real upstream UNCHANGED: claude `/v1/{path}` (incl. `POST /v1/messages/count_tokens`) and `/api/{path}`; codex `/v1/{path}`; gemini GET + `/v1beta/{path}` + the `:countTokens`/`:embedContent` verbs; ollama `/api/{path}` (incl. tags/show/pull/embeddings). `upstream_url` is RETAINED. No new stub routes; real provider creds still required.
- **C. HARD-REMOVE** the now-unused settings `embed_target`, `embed_mode`, `system_prompt` from `FrontendSettingsBase` AND remove the `OllamaFrontendSettings.embed_target` override. Grep the whole repo (incl. `apps/server/sf.json` and `SF_*_FRONTEND__` env usage, tests) and remove every reference. Validation must not break after removal.
- **D. DIRECT CUTOVER.** No feature flag. Delete the proxy/forward code on the inference leg outright; rewrite each inference handler in place. No legacy path retained.

**Minor open-question defaults (apply silently unless they conflict with A–D):**
- **O5b:** an empty `$prompt` resolution result is a FAIL-LOUD error (visible error envelope), with empty-result E2E tests on all four frontends.
- **O10:** add a TTL / re-resolution for the static-spec resolve cache; document live `active_spec`-switch behavior.
- **O12:** include a synthetic Gemini `responseId`.
- **O16:** if the active spec does not terminate in a model backend call, WARN (do not hard-fail).
- **Error visibility (#244):** render resolution errors as a NORMAL completed/200 provider envelope whose assistant text is the visible `[url4 error] ...+traceback` (most visible to the CLI). For codex this means `status="completed"` carrying the error text. NOTE: this overrides the spec's `status:"failed"` error-envelope for visibility — call it out in docs.

---

## File structure

Every file created or modified across all milestones, with its single responsibility. Paths under `apps/server/` are relative to `/Users/sergey/work/openmind/screamingface/`.

### Shared infrastructure (M1)
- **Create** `apps/server/src/screamingface/plugins/frontend_base/terminal_response.py` — SOLE location for all eight provider builders/streamers + shared helpers (`extract_error_text`, `serialize_transcript`, `estimate_tokens`, `deterministic_id`). Per-frontend modules import/re-export only.
- **Create** `apps/server/src/screamingface/plugins/frontend_base/tests/test_terminal_response.py` — unit tests for builders/streamers/helpers (independent SSE/NDJSON frame decode).
- **Create** `apps/server/src/screamingface/plugins/frontend_base/tests/test_settings_removal.py` — proves `embed_target`/`embed_mode`/`system_prompt` are gone from base + ollama settings.
- **Create** `apps/server/src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py` — proves the `(resolved_text, error_dict)` tuple contract.
- **Modify** `apps/server/src/screamingface/plugins/frontend_base/plugin_base.py` — remove the three unused settings fields from `FrontendSettingsBase`.

### claude_frontend (M2)
- **Modify** `apps/server/src/screamingface/plugins/claude_frontend/proxy.py` — rewrite `proxy_messages` terminal; delete `_forward_streaming`/`_forward_unary`/`_inject_system_context`/`_embed_context`; keep catchall + `/api/{path}` passthrough + `_extract_last_user_text`/`_replace_last_user_message`.
- **Modify** `apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py` — tuple return contract for `resolve_prompt_expression`/`resolve_static_context`; `_build_error_response` returns a dict.
- **Create** `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py` — terminal synthesis, error envelopes, passthrough regressions.
- **Modify** `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py` — migrate old forwarding tests to terminal model.
- **Modify** `apps/server/src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py` — E2E with mocked resolution.

### codex_frontend (M3)
- **Modify** `apps/server/src/screamingface/plugins/codex_frontend/proxy.py` — rewrite `proxy_responses` terminal (OpenAI Responses); delete `_inject_system_context`/`_embed_context`/`_parse_sse_response`; keep `/v1/{path}` catchall + input-fork helpers.
- **Create** `apps/server/src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py` — unary/streaming synthesis, error paths, passthrough.
- **Modify** `apps/server/src/screamingface/plugins/codex_frontend/tests/test_proxy.py` — skip/remove deleted-function tests.

### gemini_frontend (M4)
- **Modify** `apps/server/src/screamingface/plugins/gemini_frontend/proxy.py` — rewrite `proxy_gemini` with verb allow-list (only `:generateContent`/`:streamGenerateContent` terminal); delete `_inject_system_context`/`_embed_context`; keep passthrough verbs + GET + `/v1beta/{path}` catchall.
- **Modify** `apps/server/src/screamingface/plugins/gemini_frontend/plugin.py` — remove any `embed_target` override if present (covered by C grep).
- **Create** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_terminal_unary.py` — unary synthesis + error/fail-loud.
- **Create** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_terminal_streaming.py` — JSON-array default vs `?alt=sse`.
- **Create** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_passthrough.py` — `:countTokens`/`:embedContent`/GET/catchall forward.
- **Create** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_e2e.py` — E2E across unary/streaming/passthrough/error.
- **Create** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_no_upstream_inference.py` — no `generativelanguage.googleapis.com` on inference.
- **Modify** `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_proxy.py` — migrate from upstream-forward assertions.

### ollama_frontend (M5)
- **Modify** `apps/server/src/screamingface/plugins/ollama_frontend/proxy.py` — rewrite `proxy_chat` terminal (NDJSON); add `_save_session_if_needed`; delete `_inject_system_message`/`_embed_context`; keep `/api/{path}` passthrough.
- **Modify** `apps/server/src/screamingface/plugins/ollama_frontend/plugin.py` — remove `OllamaFrontendSettings.embed_target` override (C).
- **Modify** `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_proxy.py` — add terminal/error/passthrough tests; migrate old forwarding tests.

### Config (M1/C)
- **Modify** `apps/server/sf.json` — remove ollama-frontend `embed_target`/`embed_mode` keys.

### Cross-frontend, integration, docs (M6)
- **Create** `apps/server/tests/test_m6_cross_frontend_integration.py` — same spec → identical result across all four.
- **Create** `apps/server/src/screamingface/plugins/{claude,codex,gemini,ollama}_frontend/tests/test_m6_no_upstream.py` — per-frontend no-upstream-on-inference.
- **Create** `apps/server/src/screamingface/plugins/{claude,gemini,ollama}_frontend/tests/test_m6_passthrough.py` — passthrough regression.
- **Create** `apps/server/tests/test_m6_aigw_sub_calls.py` — AIGateway #245 caps apply only to ensemble sub-calls.
- **Create** `apps/server/tests/test_terminal_response_builders.py` — comprehensive builder/streamer coverage.
- **Create** `apps/server/tests/test_terminal_response_errors.py` — error-path coverage.
- **Create** `apps/server/tests/test_m6_success_criteria.py` — success-criteria checklist (optional, may live in CLAUDE.md).
- **Modify** `README.md`, per-frontend `README.md`s, `docs/configuration.md`, `docs/error-handling.md`, `CLAUDE.md`, `CHANGELOG.md` — documentation.

---

## M1: Shared terminal-response infrastructure + settings hard-remove + resolve return-contract

Create the shared `terminal_response.py` module (sole location for all eight provider response builders/streamers), hard-remove the unused settings fields (C), and pin the resolve tuple return contract used by M2–M5.

### Task 1: Create `frontend_base/terminal_response.py` with shared helpers

**Files:**
- Create: `apps/server/src/screamingface/plugins/frontend_base/terminal_response.py`

- [ ] **Step 1: Write the module**

```python
"""Shared terminal-response builders and streamers for all four frontends.

Centralizes:
- error formatting (extract_error_text)
- transcript serialization (serialize_transcript) — Decision A conversation-aware
- usage estimation (estimate_tokens) + deterministic ids (deterministic_id)
- all eight builder/streamer functions (sole location)

Per-frontend modules import and re-export only — no wire-format logic outside.
Decision A (conversation-aware): builders take optional `prompt_text` and `response_id`.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
import uuid
from typing import AsyncIterator


def extract_error_text(exc: Exception, spec_name: str, expression: str) -> str:
    """Format error text uniformly for all providers.

    Handles both httpx.HTTPStatusError (502 path) and raw Url4Interpreter exceptions.
    Returns a structured text blob with exception class, message, and full traceback.
    """
    tb_str = "".join(traceback.format_exception(exc))
    expr_preview = expression[:200] if expression else "(empty)"
    return (
        f"[url4 error] {spec_name}\n\n"
        f"Expression: {expr_preview}\n\n"
        f"Error: {exc.__class__.__name__}: {exc}\n\n"
        f"Traceback:\n{tb_str}"
    )


def serialize_transcript(turns: list[tuple[str, str]]) -> str:
    """Render conversation turns as 'User: ...\\nAssistant: ...\\n...' (Decision A).

    Args:
        turns: list of (role, text) tuples, e.g., [("user", "Hello"), ("assistant", "Hi")]

    Returns:
        Serialized transcript string for use as the $prompt blob.
    """
    lines = []
    for role, text in turns:
        role_upper = role.capitalize()
        lines.append(f"{role_upper}: {text}")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Estimate token count: max(1, len(text)//4) if text else 0."""
    return max(1, len(text) // 4) if text else 0


def deterministic_id(prefix: str, model: str, prompt_text: str, result_text: str) -> str:
    """Generate deterministic ID from model + prompt + result using SHA256.

    Returns f"{prefix}{hex_digest_first_24_chars}".
    """
    combined = model + prompt_text + result_text
    digest = hashlib.sha256(combined.encode()).hexdigest()[:24]
    return f"{prefix}{digest}"


# ============================================================================
# Anthropic (claude_frontend)
# ============================================================================

def build_anthropic_message(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> dict:
    """Build unary Anthropic Messages response envelope."""
    msg_id = response_id or deterministic_id("msg_", model, prompt_text, result_text)
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": result_text}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def stream_anthropic_sse(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> AsyncIterator[bytes]:
    """Stream Anthropic response as SSE (event: lines, blank-line terminated).

    Frame sequence:
    message_start -> ping -> content_block_start -> content_block_delta
    -> content_block_stop -> message_delta -> message_stop

    All text in ONE delta. No [DONE].
    """
    msg_id = response_id or deterministic_id("msg_", model, prompt_text, result_text)
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    def sse_frame(event_name: str, payload: dict) -> bytes:
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    yield sse_frame("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    })
    yield sse_frame("ping", {"type": "ping"})
    yield sse_frame("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    yield sse_frame("content_block_delta", {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": result_text},
    })
    yield sse_frame("content_block_stop", {
        "type": "content_block_stop",
        "index": 0,
    })
    yield sse_frame("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": output_tokens},
    })
    yield sse_frame("message_stop", {"type": "message_stop"})


# ============================================================================
# OpenAI (codex_frontend)
# ============================================================================

def build_openai_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    status: str = "completed",
) -> dict:
    """Build unary OpenAI Responses envelope.

    NOTE (#244 error visibility): error path uses status="completed" carrying the
    error text, NOT status="failed", so the Codex CLI renders the visible error.
    """
    resp_id = response_id or deterministic_id("resp_", model, prompt_text, result_text)
    item_id = deterministic_id("msg_", model, prompt_text, result_text)
    created_at = int(time.time())
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "id": resp_id,
        "object": "response",
        "created_at": created_at,
        "model": model,
        "status": status,
        "output": [
            {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": result_text,
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def stream_openai_sse(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    status: str = "completed",
) -> AsyncIterator[bytes]:
    """Stream OpenAI response as SSE (full canonical 9-event sequence).

    response.created -> response.in_progress -> response.output_item.added
    -> response.content_part.added -> response.output_text.delta
    -> response.output_text.done -> response.content_part.done
    -> response.output_item.done -> response.completed

    Every frame: data: {json}\\n\\n. Stable item_id. Monotonic sequence_number. No [DONE].
    """
    resp_id = response_id or deterministic_id("resp_", model, prompt_text, result_text)
    item_id = deterministic_id("msg_", model, prompt_text, result_text)
    created_at = int(time.time())
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)
    seq = 0

    def event(payload: dict) -> bytes:
        nonlocal seq
        payload.setdefault("sequence_number", seq)
        seq += 1
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    base_resp = {
        "id": resp_id,
        "object": "response",
        "created_at": created_at,
        "model": model,
        "output": [],
        "usage": None,
    }

    yield event({"type": "response.created", "response": {**base_resp, "status": "in_progress"}})
    yield event({"type": "response.in_progress", "response": {**base_resp, "status": "in_progress"}})
    yield event({
        "type": "response.output_item.added",
        "output_index": 0,
        "item": {"id": item_id, "type": "message", "status": "in_progress", "role": "assistant", "content": []},
    })
    yield event({
        "type": "response.content_part.added",
        "item_id": item_id,
        "output_index": 0,
        "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
    })
    yield event({
        "type": "response.output_text.delta",
        "item_id": item_id,
        "output_index": 0,
        "content_index": 0,
        "delta": result_text,
    })
    yield event({
        "type": "response.output_text.done",
        "item_id": item_id,
        "output_index": 0,
        "content_index": 0,
        "text": result_text,
    })
    yield event({
        "type": "response.content_part.done",
        "item_id": item_id,
        "output_index": 0,
        "content_index": 0,
        "part": {"type": "output_text", "text": result_text, "annotations": []},
    })
    yield event({
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "id": item_id, "type": "message", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": result_text, "annotations": []}],
        },
    })
    yield event({
        "type": "response.completed",
        "response": {
            **base_resp,
            "status": status,
            "output": [
                {
                    "id": item_id, "type": "message", "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": result_text, "annotations": []}],
                }
            ],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    })


# ============================================================================
# Google Gemini (gemini_frontend)
# ============================================================================

def build_gemini_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
) -> dict:
    """Build unary Gemini GenerateContentResponse envelope.

    O12: includes a synthetic responseId (deterministic).
    """
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)
    resp_id = response_id or deterministic_id("", model, prompt_text, result_text)

    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": result_text}]},
                "finishReason": "STOP",
                "index": 0,
                "safetyRatings": [],
            }
        ],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": input_tokens + output_tokens,
        },
        "modelVersion": model,
        "responseId": resp_id,
    }


async def stream_gemini_chunks(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
    response_id: str | None = None,
    alt_sse: bool = False,
) -> AsyncIterator[bytes]:
    """Stream Gemini response.

    Default (alt_sse=False) returns a true JSON ARRAY `[{...}]` matching Gemini's
    real streamGenerateContent REST wire format (application/json).
    With alt_sse=True, emits `data: {...}\\n\\n` for text/event-stream.
    """
    obj = build_gemini_response(result_text, model, prompt_text=prompt_text, response_id=response_id)

    if alt_sse:
        yield f"data: {json.dumps(obj)}\n\n".encode("utf-8")
    else:
        yield b"["
        yield json.dumps(obj).encode("utf-8")
        yield b"]"


# ============================================================================
# Ollama (ollama_frontend)
# ============================================================================

def build_ollama_response(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
) -> dict:
    """Build unary Ollama /api/chat response envelope.

    Ollama uses durations not tokens; durations are zero, eval counts use estimates.
    """
    created_at = "2025-06-04T00:00:00Z"
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    return {
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": result_text},
        "done": True,
        "done_reason": "stop",
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": input_tokens,
        "prompt_eval_duration": 0,
        "eval_count": output_tokens,
        "eval_duration": 0,
    }


async def stream_ollama_ndjson(
    result_text: str,
    model: str,
    *,
    prompt_text: str = "",
) -> AsyncIterator[bytes]:
    """Stream Ollama response as NDJSON (NOT SSE).

    Emits TWO complete JSON objects, each on its own line:
    1. In-progress frame with the full result_text
    2. Terminal frame with empty content, done=true
    Every frame carries a complete "message" field. Content-Type: application/x-ndjson.
    """
    created_at = "2025-06-04T00:00:00Z"
    input_tokens = estimate_tokens(prompt_text)
    output_tokens = estimate_tokens(result_text)

    yield (json.dumps({
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": result_text},
        "done": False,
    }) + "\n").encode("utf-8")

    yield (json.dumps({
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": input_tokens,
        "prompt_eval_duration": 0,
        "eval_count": output_tokens,
        "eval_duration": 0,
    }) + "\n").encode("utf-8")


__all__ = [
    "extract_error_text",
    "serialize_transcript",
    "estimate_tokens",
    "deterministic_id",
    "build_anthropic_message",
    "stream_anthropic_sse",
    "build_openai_response",
    "stream_openai_sse",
    "build_gemini_response",
    "stream_gemini_chunks",
    "build_ollama_response",
    "stream_ollama_ndjson",
]
```

- [ ] **Step 2: Verify it imports**

Run: `cd apps/server && uv run python -c "import screamingface.plugins.frontend_base.terminal_response as t; print(t.__all__)"`
Expected: prints the `__all__` list with all 12 names.

### Task 2: Unit tests for `terminal_response.py`

**Files:**
- Create: `apps/server/src/screamingface/plugins/frontend_base/tests/test_terminal_response.py`

- [ ] **Step 1: Write the test file**

```python
"""Unit tests for terminal_response builders and streamers.

Verifies envelope JSON structure per provider, usage non-zero/zeros, frame
sequence for streamers (parse SSE / NDJSON independently), and error formatting.
"""

import json
import pytest

from screamingface.plugins.frontend_base.terminal_response import (
    build_anthropic_message,
    stream_anthropic_sse,
    build_openai_response,
    stream_openai_sse,
    build_gemini_response,
    stream_gemini_chunks,
    build_ollama_response,
    stream_ollama_ndjson,
    extract_error_text,
    serialize_transcript,
    estimate_tokens,
    deterministic_id,
)


def parse_sse_frames(sse_bytes: bytes) -> list:
    text = sse_bytes.decode("utf-8")
    results = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        lines = frame.strip().split("\n")
        event_line = next((l for l in lines if l.startswith("event:")), None)
        data_line = next((l for l in lines if l.startswith("data:")), None)
        if data_line:
            event_name = event_line.replace("event:", "").strip() if event_line else None
            data_json = data_line.replace("data:", "").strip()
            try:
                results.append((event_name, json.loads(data_json)))
            except json.JSONDecodeError:
                pass
    return results


def parse_ndjson_frames(ndjson_bytes: bytes) -> list:
    text = ndjson_bytes.decode("utf-8")
    return [json.loads(line) for line in text.strip().split("\n") if line]


def test_build_anthropic_message():
    result = build_anthropic_message("Test response", "claude-3-5-sonnet", prompt_text="User: hi")
    assert result["type"] == "message"
    assert result["role"] == "assistant"
    assert result["content"][0]["text"] == "Test response"
    assert result["model"] == "claude-3-5-sonnet"
    assert result["stop_reason"] == "end_turn"
    usage = result["usage"]
    assert usage["input_tokens"] > 0  # non-zero (prompt_text supplied)
    assert usage["output_tokens"] > 0
    assert usage["cache_creation_input_tokens"] == 0
    assert usage["cache_read_input_tokens"] == 0


@pytest.mark.asyncio
async def test_stream_anthropic_sse():
    chunks = [c async for c in stream_anthropic_sse("Result text", "claude-3-5-sonnet")]
    sse_bytes = b"".join(chunks)
    frames = parse_sse_frames(sse_bytes)
    event_names = [name for name, _ in frames]
    assert event_names == ["message_start", "ping", "content_block_start", "content_block_delta",
                           "content_block_stop", "message_delta", "message_stop"]
    delta_frame = next(d for n, d in frames if n == "content_block_delta")
    assert delta_frame["delta"]["text"] == "Result text"
    assert b"[DONE]" not in sse_bytes


def test_build_openai_response():
    result = build_openai_response("Test response", "gpt-4o-mini")
    assert result["object"] == "response"
    assert result["status"] == "completed"
    assert isinstance(result["created_at"], int)
    assert result["created_at"] > 0
    assert len(result["output"]) == 1
    assert result["output"][0]["type"] == "message"
    assert result["output"][0]["status"] == "completed"
    assert result["output"][0]["content"][0]["text"] == "Test response"
    usage = result["usage"]
    for k in ("input_tokens", "output_tokens", "total_tokens", "cache_creation_input_tokens"):
        assert k in usage


def test_build_openai_response_completed_status_for_errors():
    # #244: even the error path uses status="completed" for CLI visibility
    result = build_openai_response("[url4 error] ...", "gpt-4o-mini", status="completed")
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_openai_sse():
    chunks = [c async for c in stream_openai_sse("Result", "gpt-4o-mini")]
    sse_bytes = b"".join(chunks)
    frames = parse_sse_frames(sse_bytes)
    event_names = [name for name, _ in frames]
    assert event_names == [
        "response.created", "response.in_progress", "response.output_item.added",
        "response.content_part.added", "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]
    created = next(d for n, d in frames if n == "response.created")
    assert created["response"]["status"] == "in_progress"
    completed = next(d for n, d in frames if n == "response.completed")
    assert completed["response"]["status"] == "completed"
    seq_nums = [d.get("sequence_number") for _, d in frames]
    assert seq_nums == sorted(seq_nums)
    assert b"[DONE]" not in sse_bytes


def test_build_gemini_response():
    result = build_gemini_response("Test response", "gemini-2.5-flash")
    assert result["candidates"][0]["finishReason"] == "STOP"
    assert result["candidates"][0]["content"]["role"] == "model"
    assert result["candidates"][0]["content"]["parts"][0]["text"] == "Test response"
    usage = result["usageMetadata"]
    for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"):
        assert k in usage
    assert result["modelVersion"] == "gemini-2.5-flash"
    assert "responseId" in result  # O12


@pytest.mark.asyncio
async def test_stream_gemini_chunks_default_json_array():
    chunks = [c async for c in stream_gemini_chunks("Result", "gemini-2.5-flash")]
    data = json.loads(b"".join(chunks))
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["candidates"][0]["finishReason"] == "STOP"


@pytest.mark.asyncio
async def test_stream_gemini_chunks_alt_sse():
    chunks = [c async for c in stream_gemini_chunks("Result", "gemini-2.5-flash", alt_sse=True)]
    body = b"".join(chunks)
    assert b"data: " in body
    assert b"\n\n" in body


def test_build_ollama_response():
    result = build_ollama_response("Test response", "llama3.2", prompt_text="User: hi")
    assert result["model"] == "llama3.2"
    assert result["message"]["role"] == "assistant"
    assert result["message"]["content"] == "Test response"
    assert result["done"] is True
    assert result["done_reason"] == "stop"
    assert result["total_duration"] == 0
    assert result["load_duration"] == 0
    assert result["prompt_eval_count"] >= 0
    assert result["eval_count"] > 0


@pytest.mark.asyncio
async def test_stream_ollama_ndjson():
    chunks = [c async for c in stream_ollama_ndjson("Result text", "llama3.2")]
    ndjson_bytes = b"".join(chunks)
    frames = parse_ndjson_frames(ndjson_bytes)
    assert len(frames) == 2
    assert frames[0]["done"] is False
    assert frames[0]["message"]["content"] == "Result text"
    assert frames[1]["done"] is True
    assert frames[1]["done_reason"] == "stop"
    assert frames[1]["message"]["content"] == ""
    assert "message" in frames[0] and "message" in frames[1]
    assert b"data: " not in ndjson_bytes


def test_extract_error_text():
    exc = ValueError("Test error message")
    text = extract_error_text(exc, "test-spec", "some_expression")
    assert "[url4 error]" in text
    assert "test-spec" in text
    assert "some_expression" in text
    assert "ValueError" in text
    assert "Test error message" in text
    assert "Traceback:" in text


def test_serialize_transcript():
    turns = [("user", "Hello"), ("assistant", "Hi there"), ("user", "How are you?")]
    result = serialize_transcript(turns)
    assert "User: Hello" in result
    assert "Assistant: Hi there" in result
    assert "User: How are you?" in result


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("1234") == 1
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("a") == 1


def test_deterministic_id_is_stable():
    a = deterministic_id("msg_", "m", "p", "r")
    b = deterministic_id("msg_", "m", "p", "r")
    assert a == b
    assert a.startswith("msg_")
    assert deterministic_id("msg_", "m", "p", "r2") != a
```

- [ ] **Step 2: Run tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/frontend_base/tests/test_terminal_response.py`
Expected: PASS (all tests green).

### Task 3: Hard-remove settings fields from `FrontendSettingsBase` (C)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/frontend_base/plugin_base.py`

- [ ] **Step 1: Locate the fields**

Run: `cd apps/server && grep -n "embed_target\|embed_mode\|system_prompt" src/screamingface/plugins/frontend_base/plugin_base.py`
Expected: prints the three `Field(...)` definitions (~lines 87–101).

- [ ] **Step 2: Delete the three fields**

Remove the `embed_target`, `embed_mode`, and `system_prompt` field definitions from `FrontendSettingsBase`. The base class must end after the last RETAINED field (`active_spec` through `resolve_timeout`). Do NOT remove `upstream_url`, `active_spec`, `resolve_timeout`, or `session_service_url`.

- [ ] **Step 3: Verify removal**

Run: `cd apps/server && grep -n "embed_target\|embed_mode\|system_prompt" src/screamingface/plugins/frontend_base/plugin_base.py`
Expected: no output.

### Task 4: Remove `embed_target` override from `OllamaFrontendSettings` (C)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/ollama_frontend/plugin.py`

- [ ] **Step 1: Locate and delete**

Run: `cd apps/server && grep -n "embed_target" src/screamingface/plugins/ollama_frontend/plugin.py`
Then delete the `embed_target: Literal["system", "user"] = Field(default="system")` override line.

- [ ] **Step 2: Verify**

Run: `cd apps/server && grep -n "embed_target" src/screamingface/plugins/ollama_frontend/plugin.py`
Expected: no output.

### Task 5: Remove references from `sf.json` and grep the whole repo (C)

**Files:**
- Modify: `apps/server/sf.json`

- [ ] **Step 1: Repo-wide grep for every reference**

Run: `cd /Users/sergey/work/openmind/screamingface && grep -rn "embed_target\|embed_mode\|system_prompt\|SF_.*FRONTEND__EMBED\|SF_.*FRONTEND__SYSTEM_PROMPT" apps/server/ --include="*.py" --include="*.json" | grep -v terminal_response.py | grep -v test_settings_removal.py`
Expected: shows remaining references (sf.json ollama-frontend keys, any env-var docs/tests).

- [ ] **Step 2: Remove the keys from `sf.json`**

Delete `"embed_target": ...` and `"embed_mode": ...` from the ollama-frontend block in `apps/server/sf.json`. Remove `"system_prompt"` from any frontend block that still has it.

- [ ] **Step 3: Re-grep to confirm zero references remain (except removal tests)**

Run: `cd /Users/sergey/work/openmind/screamingface && grep -rn "embed_target\|embed_mode" apps/server/ --include="*.py" --include="*.json" | grep -v test_settings_removal.py | grep -v terminal_response.py`
Expected: no output.

- [ ] **Step 4: Validate sf.json still parses and settings still load**

Run: `cd apps/server && uv run python -c "import json; json.load(open('sf.json')); print('ok')"`
Expected: `ok`.

### Task 6: Unit test for settings hard-removal

**Files:**
- Create: `apps/server/src/screamingface/plugins/frontend_base/tests/test_settings_removal.py`

- [ ] **Step 1: Write the test file**

```python
"""Test that embed_target, embed_mode, system_prompt are removed from settings (Decision C)."""

import pytest
from pydantic import ValidationError

from screamingface.plugins.frontend_base.plugin_base import FrontendSettingsBase
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.ollama_frontend.plugin import OllamaFrontendSettings


def test_frontend_settings_base_no_embed_target():
    assert "embed_target" not in FrontendSettingsBase.model_fields


def test_frontend_settings_base_no_embed_mode():
    assert "embed_mode" not in FrontendSettingsBase.model_fields


def test_frontend_settings_base_no_system_prompt():
    assert "system_prompt" not in FrontendSettingsBase.model_fields


def test_claude_settings_rejected_with_embed_target():
    with pytest.raises(ValidationError):
        ClaudeFrontendSettings(
            upstream_url="https://api.anthropic.com",
            listen_port=9101,
            embed_target="user",
        )


def test_ollama_settings_no_override():
    assert "embed_target" not in OllamaFrontendSettings.model_fields
    with pytest.raises(ValidationError):
        OllamaFrontendSettings(
            upstream_url="http://localhost:11434",
            listen_port=9104,
            embed_target="system",
        )


def test_ollama_settings_constructs_without_embed():
    settings = OllamaFrontendSettings(
        upstream_url="http://localhost:11434",
        listen_port=9104,
    )
    assert settings.upstream_url == "http://localhost:11434"
    assert settings.listen_port == 9104
    assert not hasattr(settings, "embed_target")
```

> NOTE: These rejection tests assume the settings models forbid extra fields. If the models use `model_config = ConfigDict(extra="ignore")`, the `pytest.raises(ValidationError)` assertions will not hold; in that case change those two tests to assert the field is silently dropped (`not hasattr(settings, "embed_target")`). Verify the model's `extra` policy with `grep -n "extra=" apps/server/src/screamingface/plugins/frontend_base/plugin_base.py` before running.

- [ ] **Step 2: Run tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/frontend_base/tests/test_settings_removal.py`
Expected: PASS.

### Task 7: Pin the resolve return contract in `_url4_context.py` (docstrings only)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py`

- [ ] **Step 1: Update `__all__` and add the contract note**

At the top of the file (after `__all__`), add:

```python
__all__ = ["resolve_prompt_expression", "resolve_static_context"]

# NOTE: Return contract as of M1 (implemented in M2):
# - resolve_prompt_expression: returns tuple[str | None, dict | None]
#     On success: (resolved_text_str, None)
#     On failure: (None, error_response_dict)  # provider-shaped envelope body
# - resolve_static_context: same tuple contract; None/empty static result is FAIL-LOUD (O5b).
# The handler wraps the dict in JSONResponse (unary) or routes the error text through
# the stream_<provider> generators (streaming).
```

- [ ] **Step 2: Update the two function docstrings**

Change the docstrings of `resolve_prompt_expression` and `resolve_static_context` to state the tuple contract above. Do NOT change the function bodies yet — implementation lands in M2.

- [ ] **Step 3: Type-check**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/claude_frontend/_url4_context.py 2>&1 | tail -5`
Expected: no new errors introduced.

### Task 8: Contract test scaffold for resolve helpers

**Files:**
- Create: `apps/server/src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py`

- [ ] **Step 1: Write the contract test (xfail until M2)**

```python
"""Resolve return-contract tests (Decision: tuple[str|None, dict|None]).

These are xfail until M2 implements the tuple contract in _url4_context.py.
After M2 Task 2, remove the xfail markers.
"""

import pytest
from unittest import mock

from screamingface.plugins.claude_frontend._url4_context import (
    resolve_static_context,
)


@pytest.mark.xfail(reason="Tuple contract implemented in M2 Task 2", strict=False)
def test_static_spec_none_fails_loud():
    """Static spec None/empty returns (None, error_dict) — fail-loud (O5b)."""
    plugin = mock.MagicMock()
    plugin.resolve_context.return_value = None
    settings = mock.MagicMock()
    settings.active_spec = "static-spec"

    resolved_text, error_dict = resolve_static_context(
        {"model": "test-model"},
        raw_expression="some_static_expression",
        settings=settings,
        plugin=plugin,
    )
    assert resolved_text is None
    assert isinstance(error_dict, dict)
    assert "[url4 error]" in error_dict["content"][0]["text"]
```

- [ ] **Step 2: Run (expect xfail)**

Run: `cd apps/server && uv run pytest -rx src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py`
Expected: 1 xfailed.

### Task 9: M1 gate — run all new tests, type-check, pre-commit, commit

- [ ] **Step 1: Run all M1 tests**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/frontend_base/tests/test_terminal_response.py src/screamingface/plugins/frontend_base/tests/test_settings_removal.py src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py`
Expected: all pass (resolve_contract xfailed).

- [ ] **Step 2: Type-check**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/frontend_base/terminal_response.py src/screamingface/plugins/frontend_base/plugin_base.py`
Expected: 0 errors.

- [ ] **Step 3: Pre-commit (full CI gate — ruff check AND ruff format)**

Run: `cd /Users/sergey/work/openmind/screamingface && pre-commit run --files apps/server/src/screamingface/plugins/frontend_base/terminal_response.py apps/server/src/screamingface/plugins/frontend_base/plugin_base.py apps/server/src/screamingface/plugins/ollama_frontend/plugin.py apps/server/sf.json`
Expected: all hooks pass. If ruff reformats, re-stage and re-run.

- [ ] **Step 4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M1: shared terminal_response module + hard-remove unused settings + resolve contract"
```

---

## M2: claude_frontend terminal rewrite (direct cutover)

Replace the upstream proxy leg in `claude_frontend` with in-process resolution. `proxy_messages` becomes terminal; non-inference routes keep passthrough. Uses M1's `build_anthropic_message` / `stream_anthropic_sse` / `extract_error_text` / `serialize_transcript` — no redefinitions.

**Deletions:** `_forward_streaming`, `_forward_unary`, `_inject_system_context`, `_embed_context`, inference-path upstream URL construction.
**Keep:** `/v1/{path}` catchall (incl. `POST /v1/messages/count_tokens`), `/api/{path}` passthrough, `_extract_last_user_text`, `_replace_last_user_message`.

### Task 1: Write failing terminal tests (unary, streaming, static-None)

**Files:**
- Create: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for claude_frontend terminal (ensemble-first) inference.

1. Unary and streaming inference synthesize in-memory (no api.anthropic.com).
2. Non-inference routes (catchall, count_tokens, /api/*) still forward upstream.
3. Error paths (static-None, resolution failure) return 200 with visible error text.
4. Streaming error paths terminate (message_stop frame).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def parse_sse_frames(sse_text: str) -> list:
    frames = []
    current_event = None
    current_data = None
    for line in sse_text.split("\n"):
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:"):
            try:
                current_data = json.loads(line.replace("data:", "").strip())
            except json.JSONDecodeError:
                current_data = None
        elif line.strip() == "" and current_data is not None:
            frames.append((current_event, current_data))
            current_event = None
            current_data = None
    return frames


def test_unary_inference_synthesizes_response_no_upstream_call() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)

    with patch(
        "screamingface.plugins.frontend_base.plugin_base._fetch_sync",
        return_value="Ensemble result text",
    ) as mock_fetch:
        with patch("httpx.AsyncClient.post") as mock_httpx_post:
            response = client.post("/v1/messages", json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            })

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["content"][0]["text"] == "Ensemble result text"
    assert data["model"] == "claude-opus-4-1-20250805"
    assert data["stop_reason"] == "end_turn"
    assert "usage" in data
    assert mock_fetch.called
    assert not mock_httpx_post.called


def test_streaming_inference_synthesizes_sse_no_upstream_call() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)

    with patch(
        "screamingface.plugins.frontend_base.plugin_base._fetch_sync",
        return_value="Streamed result text",
    ) as mock_fetch:
        with patch("httpx.AsyncClient.stream") as mock_httpx_stream:
            response = client.post("/v1/messages", json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "Test"}],
                "stream": True,
            })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    event_names = [n for n, _ in frames]
    assert event_names == ["message_start", "ping", "content_block_start", "content_block_delta",
                           "content_block_stop", "message_delta", "message_stop"]
    delta_frame = next(d for n, d in frames if n == "content_block_delta")
    assert delta_frame["delta"]["text"] == "Streamed result text"
    assert mock_fetch.called
    assert not mock_httpx_stream.called


def test_static_spec_none_returns_error_envelope_fail_loud() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="broken-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = "some_expression"
    mock_plugin.resolve_context.return_value = None
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)

    response = client.post("/v1/messages", json={
        "model": "claude-opus-4-1-20250805",
        "messages": [{"role": "user", "content": "Test"}],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "message"
    assert "[url4 error]" in data["content"][0]["text"]
    assert "broken-spec" in data["content"][0]["text"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py::test_unary_inference_synthesizes_response_no_upstream_call 2>&1 | head -40`
Expected: FAIL (proxy_messages still forwards upstream).

### Task 2: Implement tuple contract in `_url4_context.py`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py`

- [ ] **Step 1: Make `_build_error_response` return a dict**

```python
def _build_error_response(
    *,
    spec_name: str,
    raw_expression: str,
    exc: Exception,
) -> dict:
    """Build Anthropic-shaped error envelope dict (not JSONResponse).

    Error text lands in content[0].text so the CLI renders it (#244).
    """
    from screamingface.plugins.frontend_base.terminal_response import extract_error_text
    error_text = extract_error_text(exc, spec_name, raw_expression)
    return {
        "id": f"sf_error_{id(exc):x}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": error_text}],
        "model": "unknown",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
```

- [ ] **Step 2: Rewrite `resolve_prompt_expression` to return `(str|None, dict|None)`**

```python
async def resolve_prompt_expression(
    body: dict[str, Any],
    *,
    raw_expression: str,
    settings: Any,
    plugin: Any,
    app: Any,
    tracer: Any,
    prompt_text: str,
) -> tuple[str | None, dict | None]:
    """Substitute $prompt with a transcript blob, resolve, return (text, error_dict).

    Decision A: `prompt_text` is the FULL serialized transcript (built by the handler
    via serialize_transcript). On success returns (resolved_text, None); on any failure
    returns (None, error_envelope_dict). No body mutation; no embed_context.
    """
    with tracer.start_current_span("url4.$prompt") as prompt_span:
        try:
            backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None
            blob_key = await _store_prompt_blob(prompt_text, app=app, backend_url=backend_url, tracer=tracer)
            blob_url = f"/data/{blob_key}"
            substituted = raw_expression.replace("$prompt", blob_url)
            final_text = await _resolve_expression(substituted, app=app, backend_url=backend_url, tracer=tracer)
            logger.info("$prompt: blob=%s resolved %d chars", blob_key, len(final_text))
            if not final_text:
                # O5b: empty resolution is fail-loud
                raise RuntimeError("$prompt resolved to empty")
            return final_text, None
        except Exception as exc:
            if prompt_span and prompt_span.is_recording():
                prompt_span.set_attribute("url4.status", "error")
                prompt_span.record_exception(exc)
            logger.warning("$prompt substitution failed", exc_info=True)
            return None, _build_error_response(
                spec_name=settings.active_spec or "unknown",
                raw_expression=raw_expression,
                exc=exc,
            )
```

- [ ] **Step 3: Rewrite `resolve_static_context` to return `(str|None, dict|None)`**

```python
def resolve_static_context(
    body: dict[str, Any],
    *,
    raw_expression: str,
    settings: Any,
    plugin: Any,
) -> tuple[str | None, dict | None]:
    """Static spec: use plugin-cached resolved context. Fail-loud on None/empty (O5b)."""
    try:
        resolved_context = plugin.resolve_context() if plugin else None
        if not resolved_context:
            return None, _build_error_response(
                spec_name=settings.active_spec or "unknown",
                raw_expression=raw_expression,
                exc=RuntimeError("Static spec resolved to empty"),
            )
        logger.info("Static context resolved: %d chars", len(resolved_context))
        return resolved_context, None
    except Exception as exc:
        logger.warning("Static context resolution failed", exc_info=True)
        return None, _build_error_response(
            spec_name=settings.active_spec or "unknown",
            raw_expression=raw_expression,
            exc=exc,
        )
```

- [ ] **Step 4: Type-check**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/claude_frontend/_url4_context.py 2>&1 | tail -5`
Expected: 0 errors.

- [ ] **Step 5: Remove the xfail from the M1 resolve-contract test**

Edit `apps/server/src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py` and delete the `@pytest.mark.xfail(...)` decorator from `test_static_spec_none_fails_loud`. Run:
`cd apps/server && uv run pytest -xvs src/screamingface/plugins/frontend_base/tests/test_resolve_contract.py`
Expected: PASS.

### Task 3: Add `_extract_turns` and rewrite `proxy_messages` terminal

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/proxy.py`

- [ ] **Step 1: Add imports + `_extract_turns` helper**

At the top:

```python
from screamingface.plugins.frontend_base.terminal_response import (
    build_anthropic_message,
    stream_anthropic_sse,
    serialize_transcript,
)
```

Add near `_extract_last_user_text` (Decision A — full transcript):

```python
def _extract_turns(body: dict) -> list[tuple[str, str]]:
    """Extract conversation turns as (role, text) tuples for the $prompt blob (Decision A)."""
    turns: list[tuple[str, str]] = []
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = content if isinstance(content, str) else str(content)
        if text:
            turns.append((role, text))
    return turns
```

- [ ] **Step 2: Rewrite `proxy_messages`**

```python
@router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
async def proxy_messages(request: Request) -> Response:
    """Terminal inference handler: resolve spec, synthesize response, no upstream."""
    body = await request.json()
    is_streaming = body.get("stream", False)
    model = body.get("model", "claude-opus-4-1-20250805")

    # Stage 1: Session enrichment
    session = SessionHook.from_request(
        session_id=os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id"),
        service_url=session_service_url,
        hooks=hooks,
    )
    body = await session.enrich(body, tracer=_tracer)

    # Stage 2: URL4 resolution
    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text, error_dict = None, None

    if raw_expression and "$prompt" in raw_expression:
        turns = _extract_turns(body)  # Decision A: full transcript
        prompt_text = serialize_transcript(turns)
        if prompt_text:
            resolved_text, error_dict = await resolve_prompt_expression(
                body, raw_expression=raw_expression, settings=settings,
                plugin=plugin, app=app, tracer=_tracer, prompt_text=prompt_text,
            )
    elif raw_expression:
        resolved_text, error_dict = resolve_static_context(
            body, raw_expression=raw_expression, settings=settings, plugin=plugin,
        )

    # Stage 3: Error path (fake-200, branched on is_streaming) — #244 visibility
    if error_dict is not None:
        error_text = error_dict["content"][0]["text"]
        if is_streaming:
            return StreamingResponse(
                stream_anthropic_sse(error_text, model), media_type="text/event-stream",
            )
        return JSONResponse(content=error_dict, status_code=200)

    # Stage 4: Success
    prompt_blob = serialize_transcript(_extract_turns(body)) if raw_expression and "$prompt" in raw_expression else ""
    response_dict = build_anthropic_message(resolved_text, model, prompt_text=prompt_blob)

    if is_streaming:
        await session.save(response_dict, streaming=True, tracer=_tracer)

        async def gen():
            async for chunk in stream_anthropic_sse(resolved_text, model, prompt_text=prompt_blob):
                yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    await session.save(response_dict, streaming=False, tracer=_tracer)
    return JSONResponse(content=response_dict, status_code=200)
```

- [ ] **Step 3: Delete dead code**

Delete `_inject_system_context`, `_embed_context`, `_forward_streaming`, `_forward_unary`, and the inference-path upstream URL construction. KEEP `_extract_last_user_text`, `_replace_last_user_message`, the `/v1/{path}` catchall, and the `/api/{path}` passthrough.

- [ ] **Step 4: Verify syntax**

Run: `cd apps/server && uv run python -m py_compile src/screamingface/plugins/claude_frontend/proxy.py`
Expected: no output (compiles).

### Task 4: Run the terminal tests to green

- [ ] **Step 1: Run the three Task-1 tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py -k "unary_inference or streaming_inference or static_spec_none"`
Expected: 3 passed.

### Task 5: Passthrough regression tests

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py`

- [ ] **Step 1: Append passthrough tests**

```python
def test_count_tokens_forwards_upstream_not_terminated() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com", active_spec="test-spec")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"input_tokens": 50})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.post("/v1/messages/count_tokens", json={"messages": [{"role": "user", "content": "test"}]})
    assert response.status_code == 200
    assert response.json()["input_tokens"] == 50


def test_v1_models_forwards_upstream() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"data": [{"id": "claude-3-5-sonnet"}]})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.get("/v1/models")
    assert response.status_code == 200
    assert "data" in response.json()


def test_api_passthrough_forwards_upstream() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"users": []})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response):
        response = client.get("/api/users")
    assert response.status_code == 200
    assert "users" in response.json()
```

> NOTE: The exact httpx method the catchall uses (`request` vs `get`/`post`) depends on the existing catchall implementation. Before running, `grep -n "httpx" apps/server/src/screamingface/plugins/claude_frontend/proxy.py` and patch the method the catchall actually calls.

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py -k "forwards_upstream"`
Expected: 3 passed.

### Task 6: Streaming error termination test

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py`

- [ ] **Step 1: Append the test**

```python
def test_streaming_error_terminates_with_message_stop_frame() -> None:
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="broken-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = "bad_expression"
    mock_plugin.resolve_context.side_effect = RuntimeError("Spec eval failed")
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)

    response = client.post("/v1/messages", json={
        "model": "claude-opus-4-1-20250805",
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True,
    })

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse_frames(response.text)
    event_names = [n for n, _ in frames]
    assert "message_stop" in event_names
    assert any(
        "[url4 error]" in d.get("delta", {}).get("text", "")
        for n, d in frames if n == "content_block_delta"
    )
```

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py::test_streaming_error_terminates_with_message_stop_frame`
Expected: PASS.

### Task 7: Migrate existing `test_proxy.py`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py`

- [ ] **Step 1: Replace `test_proxy_non_streaming`**

```python
def test_proxy_non_streaming() -> None:
    """Non-streaming inference synthesizes response; no upstream call."""
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = None
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com", active_spec="test-spec")
    app = FastAPI()
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)
    with patch("screamingface.plugins.frontend_base.plugin_base._fetch_sync", return_value="Synthesized response"):
        with patch("httpx.AsyncClient.post") as mock_post:
            resp = client.post("/v1/messages", json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert not mock_post.called
```

> NOTE: With `get_active_expression()` returning `None`, no resolution happens and `resolved_text` is `None`. The handler must still produce a valid envelope (empty/passthrough content). If your final handler routes no-spec requests to upstream forwarding instead, change this test to assert the no-spec passthrough behavior. Decide the no-spec policy explicitly in Task 3 and keep this test consistent.

- [ ] **Step 2: Replace `test_proxy_forwards_headers` with a catchall-only header test**

```python
def test_proxy_forwards_headers_on_catchall() -> None:
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"data": []})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response) as mock_req:
        client.get("/v1/models", headers={"anthropic-version": "2023-06-01", "authorization": "Bearer test"})
    sent_headers = mock_req.call_args.kwargs.get("headers", {})
    assert sent_headers.get("anthropic-version") == "2023-06-01"
    assert sent_headers.get("authorization") == "Bearer test"
```

- [ ] **Step 3: Run the migrated tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_proxy.py -k "non_streaming or forwards_headers_on_catchall or does_not_inject_env_api_key"`
Expected: all pass.

### Task 8: E2E tests with mocked resolution

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py`

- [ ] **Step 1: Append E2E tests**

```python
def test_e2e_prompt_spec_unary_no_upstream() -> None:
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = '/claude($prompt)!"[end]" | /collect'
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)
    with patch("screamingface.plugins.frontend_base.plugin_base._fetch_sync", return_value="Ensemble answer: the test passed"):
        with patch("httpx.AsyncClient") as mock_client:
            resp = client.post("/v1/messages", json={
                "model": "claude-opus-4-1-20250805",
                "messages": [{"role": "user", "content": "What is 2+2?"}],
            })
    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "Ensemble answer: the test passed"
    assert not mock_client.called or all("api.anthropic.com" not in str(c) for c in mock_client.call_args_list)


def test_e2e_prompt_spec_streaming_no_upstream() -> None:
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = '/claude($prompt)!"done" | /collect'
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec",
        backend_url="http://localhost:8000",
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)
    with patch("screamingface.plugins.frontend_base.plugin_base._fetch_sync", return_value="Streamed result"):
        resp = client.post("/v1/messages", json={
            "model": "claude-opus-4-1-20250805",
            "messages": [{"role": "user", "content": "Stream this"}],
            "stream": True,
        })
    assert resp.status_code == 200
    assert "message_stop" in resp.text
```

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py -k "prompt_spec"`
Expected: pass.

### Task 9: M2 gate — full suite, type-check, pre-commit, commit

- [ ] **Step 1: Full claude_frontend suite**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/claude_frontend/tests/`
Expected: all pass.

- [ ] **Step 2: Type-check**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/claude_frontend/proxy.py src/screamingface/plugins/claude_frontend/_url4_context.py`
Expected: 0 errors.

- [ ] **Step 3: Pre-commit**

Run: `cd /Users/sergey/work/openmind/screamingface && pre-commit run --files apps/server/src/screamingface/plugins/claude_frontend/proxy.py apps/server/src/screamingface/plugins/claude_frontend/_url4_context.py apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy_terminal.py`
Expected: pass (re-stage if ruff-format edits).

- [ ] **Step 4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M2: claude_frontend terminal rewrite (direct cutover, conversation-aware)"
```

---

## M3: codex_frontend terminal rewrite (OpenAI Responses)

Rewrite `proxy_responses` to resolve in-process and synthesize OpenAI Responses envelopes using M1's `build_openai_response` / `stream_openai_sse` / `extract_error_text` / `serialize_transcript`. Keep `/v1/{path}` catchall passthrough. **#244 override:** error path uses `status="completed"` carrying the error text.

**Deletions:** `_inject_system_context`, `_embed_context`, `_parse_sse_response`, inference upstream forwarding.
**Keep:** `_extract_last_user_text`, `_replace_user_text`, `_build_headers`, `/v1/{path}` catchall.

### Task 1: Add `_extract_turns` helper + failing unary test

**Files:**
- Modify: `apps/server/src/screamingface/plugins/codex_frontend/proxy.py` (add helper)
- Create: `apps/server/src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py`

- [ ] **Step 1: Add `_extract_turns` to codex proxy.py**

Add a codex-shaped transcript extractor (codex uses `input` and/or `messages`):

```python
def _extract_turns(body: dict) -> list[tuple[str, str]]:
    """Extract conversation turns (role, text) for the $prompt blob (Decision A).

    Codex `input` may be a string or a list of message items.
    """
    turns: list[tuple[str, str]] = []
    inp = body.get("input")
    if isinstance(inp, str) and inp:
        turns.append(("user", inp))
    elif isinstance(inp, list):
        for item in inp:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, list):
                text = "".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") in ("input_text", "output_text", "text")
                )
            else:
                text = content if isinstance(content, str) else str(content)
            if text:
                turns.append((role, text))
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        text = content if isinstance(content, str) else str(content)
        if text:
            turns.append((role, text))
    return turns
```

- [ ] **Step 2: Create the test file with the unary success test**

```python
"""Tests for codex-frontend terminal inference (direct cutover).

1. POST /v1/responses resolves the spec in-process; NO upstream call.
2. Unary + streaming paths.
3. Error paths render visible error text (HTTP 200, status="completed").
4. Non-inference /v1/{path} still forwards upstream.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse


def _make_settings():
    settings = MagicMock()
    settings.upstream_url = "https://api.openai.com"
    settings.listen_port = 9102
    settings.backend_url = None
    settings.resolve_timeout = 1200.0
    settings.session_service_url = None
    settings.active_spec = "test-spec"
    return settings


async def _call_route(router, path, request):
    for route in router.routes:
        if getattr(route, "path", None) == path:
            return await route.endpoint(request)
    raise AssertionError(f"route {path} not found")


@pytest.mark.asyncio
async def test_proxy_responses_unary_success_no_upstream_call():
    from screamingface.plugins.codex_frontend.proxy import create_router
    settings = _make_settings()
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "/codex(model='gpt-4o-mini')!robots.txt"
    app = MagicMock()
    app.state.blob_store = MagicMock()
    app.state.blob_store.store.return_value = "blob_123"
    hooks = MagicMock()
    hooks.emit_async = AsyncMock(return_value=[None])
    router = create_router(settings=settings, app=app, plugin=plugin, hooks=hooks)

    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"input": "GET /robots.txt", "model": "gpt-4o-mini", "stream": False})
    request.headers = {"x-session-id": "s"}
    request.url.query = ""
    request.method = "POST"
    request.app = app

    with patch("screamingface.plugins.codex_frontend.proxy.httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        with patch("screamingface.plugins.codex_frontend.proxy.Url4Interpreter") as mock_interp:
            mock_interp.return_value.evaluate = AsyncMock(return_value="User-agent: *\nDisallow: /")
            response = await _call_route(router, "/v1/responses", request)

    assert not mock_client.post.called
    assert not mock_client.stream.called
    assert isinstance(response, JSONResponse)
    rj = json.loads(response.body)
    assert rj["object"] == "response"
    assert rj["status"] == "completed"
    assert isinstance(rj["created_at"], int) and rj["created_at"] > 0
    assert rj["output"][0]["content"][0]["text"] == "User-agent: *\nDisallow: /"
    usage = rj["usage"]
    assert "input_tokens" in usage and "output_tokens" in usage and "total_tokens" in usage
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py::test_proxy_responses_unary_success_no_upstream_call`
Expected: FAIL.

### Task 2: Add failing streaming + error + passthrough tests

**Files:**
- Modify: `apps/server/src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py`

- [ ] **Step 1: Append streaming success test**

```python
@pytest.mark.asyncio
async def test_proxy_responses_streaming_success_no_upstream_call():
    from screamingface.plugins.codex_frontend.proxy import create_router
    settings = _make_settings()
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "/codex(model='gpt-4o-mini')!robots.txt"
    app = MagicMock()
    app.state.blob_store = MagicMock()
    app.state.blob_store.store.return_value = "blob_456"
    hooks = MagicMock()
    hooks.emit_async = AsyncMock(return_value=[None])
    router = create_router(settings=settings, app=app, plugin=plugin, hooks=hooks)

    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"input": "Stream test", "model": "gpt-4o-mini", "stream": True})
    request.headers = {"x-session-id": "t"}
    request.url.query = ""
    request.method = "POST"
    request.app = app

    with patch("screamingface.plugins.codex_frontend.proxy.httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        with patch("screamingface.plugins.codex_frontend.proxy.Url4Interpreter") as mock_interp:
            mock_interp.return_value.evaluate = AsyncMock(return_value="Streaming result text")
            response = await _call_route(router, "/v1/responses", request)

    assert not mock_client.stream.called and not mock_client.post.called
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    chunks = [c async for c in response.body_iterator]
    sse_text = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode("utf-8")
    event_types = []
    for frame in sse_text.split("\n\n"):
        for line in frame.strip().split("\n"):
            if line.startswith("data:"):
                try:
                    event_types.append(json.loads(line[5:].strip()).get("type"))
                except Exception:
                    pass
    assert event_types == [
        "response.created", "response.in_progress", "response.output_item.added",
        "response.content_part.added", "response.output_text.delta", "response.output_text.done",
        "response.content_part.done", "response.output_item.done", "response.completed",
    ]
    assert "[DONE]" not in sse_text
```

- [ ] **Step 2: Append unary + streaming error tests (status="completed", #244)**

```python
@pytest.mark.asyncio
async def test_proxy_responses_error_unary_visible_text():
    from screamingface.plugins.codex_frontend.proxy import create_router
    settings = _make_settings()
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "/codex(bad_expr)!error"
    app = MagicMock()
    app.state.blob_store = MagicMock()
    app.state.blob_store.store.return_value = "blob_err"
    hooks = MagicMock()
    hooks.emit_async = AsyncMock(return_value=[None])
    router = create_router(settings=settings, app=app, plugin=plugin, hooks=hooks)

    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"input": "Will fail", "model": "gpt-4o-mini", "stream": False})
    request.headers = {"x-session-id": "e"}
    request.url.query = ""
    request.method = "POST"
    request.app = app

    with patch("screamingface.plugins.codex_frontend.proxy.httpx.AsyncClient"):
        with patch("screamingface.plugins.codex_frontend.proxy.Url4Interpreter") as mock_interp:
            mock_interp.return_value.evaluate = AsyncMock(side_effect=ValueError("Invalid expression syntax"))
            response = await _call_route(router, "/v1/responses", request)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    rj = json.loads(response.body)
    assert rj["status"] == "completed"  # #244 override (NOT "failed")
    error_text = rj["output"][0]["content"][0]["text"]
    assert "[url4 error]" in error_text
    assert "ValueError" in error_text or "Invalid expression" in error_text


@pytest.mark.asyncio
async def test_proxy_responses_error_streaming_terminating_frame():
    from screamingface.plugins.codex_frontend.proxy import create_router
    settings = _make_settings()
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "/codex()!error_spec"
    app = MagicMock()
    app.state.blob_store = MagicMock()
    hooks = MagicMock()
    hooks.emit_async = AsyncMock(return_value=[None])
    router = create_router(settings=settings, app=app, plugin=plugin, hooks=hooks)

    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value={"input": "Streaming error", "model": "gpt-4o-mini", "stream": True})
    request.headers = {}
    request.url.query = ""
    request.method = "POST"
    request.app = app

    with patch("screamingface.plugins.codex_frontend.proxy.Url4Interpreter") as mock_interp:
        mock_interp.return_value.evaluate = AsyncMock(side_effect=RuntimeError("Spec resolution timeout"))
        response = await _call_route(router, "/v1/responses", request)

    assert isinstance(response, StreamingResponse)
    chunks = [c async for c in response.body_iterator]
    sse_text = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks).decode("utf-8")
    events = []
    for frame in sse_text.split("\n\n"):
        for line in frame.strip().split("\n"):
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
    assert any(e.get("type") == "response.completed" for e in events)
    delta = next((e for e in events if e.get("type") == "response.output_text.delta"), None)
    assert delta is not None
    assert "[url4 error]" in delta.get("delta", "") or "Spec resolution" in delta.get("delta", "")
```

- [ ] **Step 3: Append catchall passthrough test**

```python
@pytest.mark.asyncio
async def test_proxy_catchall_forwards_upstream_unchanged():
    from screamingface.plugins.codex_frontend.proxy import create_router
    settings = _make_settings()
    plugin = MagicMock()
    router = create_router(settings=settings, app=None, plugin=plugin, hooks=None)

    request = MagicMock(spec=Request)
    request.method = "GET"
    request.headers = {}
    request.url.query = ""
    request.body = AsyncMock(return_value=b"")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"object": "list", "data": [{"id": "gpt-4o-mini"}]}
    mock_response.headers = {"content-type": "application/json"}
    mock_response.content = json.dumps(mock_response.json()).encode()

    with patch("screamingface.plugins.codex_frontend.proxy.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        response = await _call_route(router, "/v1/{path:path}", _patch_path(request, "models"))

    assert mock_client.request.called


def _patch_path(request, path):
    # helper: the catchall endpoint signature is endpoint(request, path=...)
    request._catchall_path = path
    return request
```

> NOTE: The catchall endpoint takes `path` as a path param. Adjust `_call_route`/`_patch_path` to call `route.endpoint(request, path="models")` for the catchall route specifically. Inspect the real signature with `grep -n "def .*path" apps/server/src/screamingface/plugins/codex_frontend/proxy.py`.

- [ ] **Step 4: Run all (expect FAIL until Task 3)**

Run: `cd apps/server && uv run pytest -x src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py 2>&1 | tail -20`
Expected: failures (handler not rewritten).

### Task 3: Rewrite `proxy_responses` handler

**Files:**
- Modify: `apps/server/src/screamingface/plugins/codex_frontend/proxy.py`

- [ ] **Step 1: Rewrite the handler**

```python
@router.post("/v1/responses", response_model=None, operation_id="proxy_responses")
async def proxy_responses(request: Request) -> Response:
    """Codex inference handler: resolve spec in-process, synthesize OpenAI Responses envelope."""
    from screamingface.plugins.frontend_base.terminal_response import (
        build_openai_response, stream_openai_sse, extract_error_text, serialize_transcript,
    )

    body = await request.json()
    is_streaming = body.get("stream", False)
    model = body.get("model", "unknown")

    # Session enrichment
    session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
    original_user_msg = None
    if session_id and settings.session_service_url and hooks:
        original_user_msg = _extract_last_user_text(body)
        try:
            results = await hooks.emit_async(
                "session.enrich_request", body=body, session_id=session_id,
                session_service_url=settings.session_service_url,
            )
            for result in results:
                if result is not None:
                    body = result
                    break
        except Exception:
            logger.warning("Session enrichment failed for %s", session_id, exc_info=True)

    # URL4 resolution
    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text = None
    error_exc = None
    prompt_text = ""

    if raw_expression:
        try:
            if "$prompt" in raw_expression:
                turns = _extract_turns(body)            # Decision A: full transcript
                prompt_text = serialize_transcript(turns)
                if prompt_text:
                    if settings.backend_url:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=False) as dc:
                            blob_resp = await dc.post(
                                f"{settings.backend_url.rstrip('/')}/data",
                                content=prompt_text.encode("utf-8"),
                                headers={"content-type": "text/plain; charset=utf-8"},
                            )
                            blob_resp.raise_for_status()
                            blob_key = blob_resp.json()["key"]
                    else:
                        blob_key = app.state.blob_store.store(
                            prompt_text.encode("utf-8"), "text/plain; charset=utf-8"
                        )
                    substituted = raw_expression.replace("$prompt", f"/data/{blob_key}")
                    if settings.backend_url:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.resolve_timeout), verify=False) as ec:
                            ens_resp = await ec.get(f"{settings.backend_url.rstrip('/')}/ensemble", params={"q": substituted})
                            ens_resp.raise_for_status()
                            resolved_text = ens_resp.text
                    else:
                        interpreter = Url4Interpreter(app=app)
                        resolved_text = await interpreter.evaluate(substituted)
                    if not resolved_text:
                        raise RuntimeError("$prompt resolved to empty (fail-loud)")
            else:
                resolved_text = plugin.resolve_context() if plugin else None
                if not resolved_text:
                    raise RuntimeError("Static spec resolved to empty (fail-loud)")
        except Exception as exc:
            error_exc = exc

    # Error path — #244: status="completed" carrying the error text
    if error_exc is not None:
        error_text = extract_error_text(error_exc, settings.active_spec or "unknown-spec", raw_expression or "")
        if is_streaming:
            return StreamingResponse(
                stream_openai_sse(error_text, model, prompt_text=prompt_text, status="completed"),
                media_type="text/event-stream",
            )
        return JSONResponse(
            content=build_openai_response(error_text, model, prompt_text=prompt_text, status="completed"),
            status_code=200,
        )

    # Success path
    response_dict = build_openai_response(resolved_text or "", model, prompt_text=prompt_text)

    async def _save():
        if session_id and settings.session_service_url and hooks and original_user_msg:
            try:
                await hooks.emit_async(
                    "session.save_response", session_id=session_id,
                    session_service_url=settings.session_service_url,
                    user_message_body=original_user_msg, response_body=response_dict,
                )
            except Exception:
                logger.warning("Session save failed for %s", session_id, exc_info=True)

    if is_streaming:
        async def gen():
            async for chunk in stream_openai_sse(resolved_text or "", model, prompt_text=prompt_text):
                yield chunk
        await _save()
        return StreamingResponse(gen(), media_type="text/event-stream")

    await _save()
    return JSONResponse(content=response_dict, status_code=200)
```

- [ ] **Step 2: Delete dead code**

Delete `_inject_system_context`, `_embed_context`, `_parse_sse_response`, and the inference upstream-forwarding block. KEEP `_extract_last_user_text`, `_replace_user_text`, `_build_headers`, and the `/v1/{path}` catchall. Ensure `from screamingface.plugins.url4_executor.interpreter import Url4Interpreter` is imported at module level so the test's `proxy.Url4Interpreter` patch target exists.

- [ ] **Step 3: Verify syntax**

Run: `cd apps/server && uv run python -m py_compile src/screamingface/plugins/codex_frontend/proxy.py`
Expected: compiles.

- [ ] **Step 4: Run all terminal tests**

Run: `cd apps/server && uv run pytest -x src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py`
Expected: all pass.

### Task 4: Migrate existing `test_proxy.py`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/codex_frontend/tests/test_proxy.py`

- [ ] **Step 1: Remove imports of deleted functions and skip obsolete classes**

Remove any `from ...proxy import _parse_sse_response, _embed_context, _inject_system_context`. For any test class targeting those, mark:

```python
import pytest

@pytest.mark.skip(reason="Function deleted in M3 terminal rewrite")
class TestParseSSEResponse: pass

@pytest.mark.skip(reason="Function deleted in M3 terminal rewrite")
class TestEmbedContext: pass
```

Keep `TestExtractLastUserText` and `TestReplaceUserText`.

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/codex_frontend/tests/test_proxy.py`
Expected: pass (obsolete tests skipped).

### Task 5: M3 gate — type-check, pre-commit, commit

- [ ] **Step 1: Type-check**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/codex_frontend/proxy.py`
Expected: 0 errors.

- [ ] **Step 2: Pre-commit**

Run: `cd /Users/sergey/work/openmind/screamingface && pre-commit run --files apps/server/src/screamingface/plugins/codex_frontend/proxy.py apps/server/src/screamingface/plugins/codex_frontend/tests/test_terminal_inference.py apps/server/src/screamingface/plugins/codex_frontend/tests/test_proxy.py`
Expected: pass.

- [ ] **Step 3: Full codex suite + commit**

```bash
cd apps/server && uv run pytest -q src/screamingface/plugins/codex_frontend/tests/
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M3: codex_frontend terminal rewrite (OpenAI Responses, conversation-aware)"
```

---

## M4: gemini_frontend terminal rewrite (verb allow-list)

Rewrite `proxy_gemini` so only `:generateContent` / `:streamGenerateContent` are terminal; everything else (GET, `:countTokens`, `:embedContent`, `/v1beta/{path}`) forwards upstream. Default streaming = JSON ARRAY (`application/json`); `?alt=sse` = SSE. Uses M1's `build_gemini_response` / `stream_gemini_chunks` / `extract_error_text` / `serialize_transcript`. Gemini stays **save-less**.

**Deletions:** `_inject_system_context`, `_embed_context`.
**Keep:** `_extract_last_user_text`/`_replace_user_text`, `_build_headers`, GET + non-generate verb passthrough, `/v1beta/{path}` catchall.

### Task 1: Failing unary tests

**Files:**
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_terminal_unary.py`

- [ ] **Step 1: Write the test file**

```python
"""gemini_frontend unary :generateContent terminal inference."""

import pytest
from unittest import mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.proxy import create_router
from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings


@pytest.fixture
def gemini_settings():
    return GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        listen_port=9103, backend_url="http://localhost:8000", active_spec="test-spec",
    )


@pytest.fixture
def mock_plugin():
    plugin = mock.MagicMock()
    plugin.get_active_expression.return_value = "/echo('Static result')"
    plugin.resolve_context.return_value = "Static resolved text"
    return plugin


@pytest.fixture
def mock_hooks():
    hooks = mock.MagicMock()
    hooks.emit_async = mock.AsyncMock(return_value=[])
    return hooks


@pytest.fixture
def app(gemini_settings, mock_plugin, mock_hooks):
    a = FastAPI()
    a.state.blob_store = None
    a.include_router(create_router(settings=gemini_settings, app=a, plugin=mock_plugin, hooks=mock_hooks))
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_unary_generate_content_no_upstream_call(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mock_interp:
        mock_interp.return_value.evaluate = mock.AsyncMock(return_value="Result from ensemble")
        with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient"):
            response = client.post(
                "/v1beta/models/gemini-2.5-flash:generateContent",
                json={"contents": [{"role": "user", "parts": [{"text": "What is 2+2?"}]}]},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["candidates"][0]["finishReason"] == "STOP"
    assert data["candidates"][0]["content"]["role"] == "model"
    assert data["candidates"][0]["content"]["parts"][0]["text"] == "Result from ensemble"
    assert "usageMetadata" in data
    assert data["modelVersion"] == "gemini-2.5-flash"
    assert "responseId" in data  # O12


def test_unary_static_spec_resolved_locally(client, mock_plugin):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient"):
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:generateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]},
        )
    assert response.status_code == 200
    assert response.json()["candidates"][0]["content"]["parts"][0]["text"] == "Static resolved text"
    mock_plugin.resolve_context.assert_called_once()


def test_unary_error_on_resolution_timeout(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mock_interp:
        mock_interp.return_value.evaluate = mock.AsyncMock(side_effect=TimeoutError("Spec resolution timed out"))
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:generateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "Test"}]}]},
        )
    assert response.status_code == 200
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    assert "[url4 error]" in text and "TimeoutError" in text


def test_unary_static_none_is_fail_loud(client, mock_plugin):
    mock_plugin.resolve_context.return_value = None
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient"):
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:generateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "Test"}]}]},
        )
    assert response.status_code == 200
    assert "[url4 error]" in response.json()["candidates"][0]["content"]["parts"][0]["text"]
```

> NOTE: The unary spec uses `/echo('Static result')` which contains no `$prompt`, so the static path runs and `mock_plugin.resolve_context` returns `"Static resolved text"`. The interpreter mock only matters for `$prompt` tests; both branches must route through resolution, never upstream.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/gemini_frontend/tests/test_terminal_unary.py::test_unary_generate_content_no_upstream_call`
Expected: FAIL.

### Task 2: Implement `proxy_gemini` (verb allow-list + unary + streaming)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/gemini_frontend/proxy.py`

- [ ] **Step 1: Add imports and `_extract_turns`**

```python
from screamingface.plugins.frontend_base.terminal_response import (
    build_gemini_response, stream_gemini_chunks, extract_error_text, serialize_transcript,
)
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter


def _extract_turns(body: dict) -> list[tuple[str, str]]:
    """Extract turns (role, text) from Gemini `contents` for the $prompt blob (Decision A)."""
    turns: list[tuple[str, str]] = []
    for item in body.get("contents", []):
        role = item.get("role", "user")
        parts = item.get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text:
            turns.append((role, text))
    return turns
```

- [ ] **Step 2: Rewrite `proxy_gemini`**

```python
@router.api_route(
    "/v1beta/models/{model_path:path}",
    methods=["GET", "POST"],
    response_model=None,
    operation_id="proxy_gemini",
)
async def proxy_gemini(request: Request, model_path: str) -> Response:
    """Gemini: terminal inference (:generateContent / :streamGenerateContent) vs passthrough."""
    is_generate = model_path.endswith(":generateContent")
    is_stream_generate = model_path.endswith(":streamGenerateContent")
    is_inference = is_generate or is_stream_generate

    # --- Passthrough (GET, :countTokens, :embedContent, etc.) ---
    if request.method == "GET" or not is_inference:
        url = f"{upstream_url}/v1beta/models/{model_path}"
        qs = str(request.url.query)
        if qs:
            url = f"{url}?{qs}"
        headers = _build_headers(request)
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        if request.method == "GET":
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.get(url, headers=headers)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        body_bytes = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body_bytes:
            kwargs["content"] = body_bytes
        async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
            resp = await client.post(url, **kwargs)
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        return Response(content=resp.content, status_code=resp.status_code, media_type=ct)

    # --- Inference path (terminal) ---
    body = await request.json()
    model_name = model_path.split(":")[0].split("/")[-1]

    # Session enrichment (gemini stays save-less; enrich only)
    session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
    if session_id and session_service_url and hooks:
        try:
            results = await hooks.emit_async(
                "session.enrich_request", body=body, session_id=session_id,
                session_service_url=session_service_url,
            )
            for result in results:
                if result is not None:
                    body = result
                    break
        except Exception:
            logger.warning("Session enrichment failed", exc_info=True)

    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text = None
    error_text = None
    prompt_text = ""

    if raw_expression and "$prompt" in raw_expression:
        try:
            turns = _extract_turns(body)               # Decision A
            prompt_text = serialize_transcript(turns)
            if prompt_text:
                backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None
                if backend_url:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=False) as dc:
                        blob_resp = await dc.post(
                            f"{backend_url}/data",
                            content=prompt_text.encode("utf-8"),
                            headers={"content-type": "text/plain; charset=utf-8"},
                        )
                        blob_resp.raise_for_status()
                        blob_key = blob_resp.json()["key"]
                else:
                    blob_key = request.app.state.blob_store.store(
                        prompt_text.encode("utf-8"), "text/plain; charset=utf-8"
                    )
                substituted = raw_expression.replace("$prompt", f"/data/{blob_key}")
                if backend_url:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.resolve_timeout or 1200.0), verify=False) as ec:
                        ens_resp = await ec.get(f"{backend_url}/ensemble", params={"q": substituted})
                        ens_resp.raise_for_status()
                        resolved_text = ens_resp.text
                else:
                    resolved_text = await Url4Interpreter(app=app).evaluate(substituted)
                if not resolved_text:
                    raise RuntimeError("$prompt resolved to empty (fail-loud)")
        except Exception as exc:
            logger.warning("$prompt resolution failed", exc_info=True)
            error_text = extract_error_text(exc, settings.active_spec or "gemini-spec", raw_expression or "")
    elif raw_expression:
        try:
            resolved_text = plugin.resolve_context() if plugin else None
            if not resolved_text:
                raise RuntimeError("Static spec resolved to empty")
        except Exception as exc:
            logger.warning("Static spec resolution failed", exc_info=True)
            error_text = extract_error_text(exc, settings.active_spec or "gemini-spec", raw_expression or "")

    alt_sse = "alt=sse" in str(request.url.query)

    # Error path
    if error_text:
        if is_stream_generate:
            media = "text/event-stream" if alt_sse else "application/json"
            return StreamingResponse(
                stream_gemini_chunks(error_text, model_name, alt_sse=alt_sse), media_type=media,
            )
        return JSONResponse(content=build_gemini_response(error_text, model_name), status_code=200)

    if not resolved_text:
        resolved_text = ""

    # Success path
    if is_stream_generate:
        media = "text/event-stream" if alt_sse else "application/json"
        return StreamingResponse(
            stream_gemini_chunks(resolved_text, model_name, prompt_text=prompt_text, alt_sse=alt_sse),
            media_type=media,
        )
    return JSONResponse(content=build_gemini_response(resolved_text, model_name, prompt_text=prompt_text), status_code=200)
```

- [ ] **Step 3: Delete `_inject_system_context` and `_embed_context`**

Remove both helpers. KEEP `_extract_last_user_text`, `_replace_user_text`, `_build_headers`, and the `/v1beta/{path}` catchall (non-`models` paths).

- [ ] **Step 4: Run unary tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/gemini_frontend/tests/test_terminal_unary.py`
Expected: all pass.

### Task 3: Streaming tests + verify

**Files:**
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_terminal_streaming.py`

- [ ] **Step 1: Write the test file**

```python
"""gemini_frontend streaming :streamGenerateContent terminal inference."""

import json
import pytest
from unittest import mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.proxy import create_router
from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings


@pytest.fixture
def gemini_settings():
    return GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        listen_port=9103, backend_url="http://localhost:8000", active_spec="test-spec",
    )


@pytest.fixture
def mock_plugin():
    plugin = mock.MagicMock()
    plugin.get_active_expression.return_value = "/echo('Streaming result')"
    plugin.resolve_context.return_value = "Streamed text result"
    return plugin


@pytest.fixture
def app(gemini_settings, mock_plugin):
    hooks = mock.MagicMock()
    hooks.emit_async = mock.AsyncMock(return_value=[])
    a = FastAPI()
    a.state.blob_store = None
    a.include_router(create_router(settings=gemini_settings, app=a, plugin=mock_plugin, hooks=hooks))
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_streaming_default_json_array(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(return_value="Streaming result text")
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:streamGenerateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "Q"}]}]},
        )
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/json"
    data = json.loads(response.text)
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["candidates"][0]["finishReason"] == "STOP"


def test_streaming_alt_sse_format(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(return_value="SSE result text")
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse",
            json={"contents": [{"role": "user", "parts": [{"text": "T"}]}]},
        )
    assert response.status_code == 200
    assert response.headers.get("content-type").startswith("text/event-stream")
    assert "data: " in response.text and "\n\n" in response.text


def test_streaming_error_includes_terminating_frame(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(side_effect=ValueError("Evaluation failed"))
        response = client.post(
            "/v1beta/models/gemini-2.5-flash:streamGenerateContent",
            json={"contents": [{"role": "user", "parts": [{"text": "T"}]}]},
        )
    assert response.status_code == 200
    data = json.loads(response.text)
    assert "[url4 error]" in data[0]["candidates"][0]["content"]["parts"][0]["text"]
```

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/gemini_frontend/tests/test_terminal_streaming.py`
Expected: pass.

### Task 4: Passthrough + no-upstream + E2E tests

**Files:**
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_passthrough.py`
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_no_upstream_inference.py`
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_e2e.py`

- [ ] **Step 1: Write `test_passthrough.py`**

```python
"""gemini_frontend passthrough verbs forward upstream; inference does not."""

import pytest
from unittest import mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.proxy import create_router
from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings


@pytest.fixture
def client():
    settings = GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        listen_port=9103, backend_url="http://localhost:8000", active_spec="test-spec",
    )
    plugin = mock.MagicMock()
    plugin.get_active_expression.return_value = "/echo('Spec result')"
    hooks = mock.MagicMock()
    hooks.emit_async = mock.AsyncMock(return_value=[])
    a = FastAPI()
    a.state.blob_store = None
    a.include_router(create_router(settings=settings, app=a, plugin=plugin, hooks=hooks))
    return TestClient(a)


def test_count_tokens_forwards_upstream(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient") as mc:
        resp = mock.AsyncMock()
        resp.json.return_value = {"totalTokens": 42}
        mc.return_value.__aenter__.return_value.post.return_value = resp
        r = client.post("/v1beta/models/gemini-2.5-flash:countTokens",
                        json={"contents": [{"role": "user", "parts": [{"text": "test"}]}]})
    assert r.status_code == 200
    assert r.json() == {"totalTokens": 42}
    mc.assert_called_once()


def test_embed_content_forwards_upstream(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient") as mc:
        resp = mock.AsyncMock()
        resp.json.return_value = {"embeddings": [{"values": [0.1, 0.2]}]}
        mc.return_value.__aenter__.return_value.post.return_value = resp
        r = client.post("/v1beta/models/embedding-001:embedContent", json={"texts": ["hi"]})
    assert r.status_code == 200
    assert "embeddings" in r.json()


def test_get_model_metadata_forwards_upstream(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient") as mc:
        resp = mock.AsyncMock()
        resp.json.return_value = {"name": "models/gemini-2.5-flash"}
        mc.return_value.__aenter__.return_value.get.return_value = resp
        r = client.get("/v1beta/models/gemini-2.5-flash")
    assert r.status_code == 200
    assert r.json()["name"] == "models/gemini-2.5-flash"


def test_generate_content_not_forwarded_upstream(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(return_value="AI is...")
        with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient"):
            r = client.post("/v1beta/models/gemini-2.5-flash:generateContent",
                            json={"contents": [{"role": "user", "parts": [{"text": "What is AI?"}]}]})
    assert r.status_code == 200
```

- [ ] **Step 2: Write `test_no_upstream_inference.py`**

```python
"""Verify gemini inference never calls generativelanguage.googleapis.com."""

import pytest
from unittest import mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.proxy import create_router
from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings


@pytest.fixture
def client():
    settings = GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        listen_port=9103, backend_url="http://localhost:8000", active_spec="test-spec",
    )
    plugin = mock.MagicMock()
    plugin.get_active_expression.return_value = "/echo('No upstream')"
    plugin.resolve_context.return_value = "Resolved locally"
    hooks = mock.MagicMock()
    hooks.emit_async = mock.AsyncMock(return_value=[])
    a = FastAPI()
    a.state.blob_store = None
    a.include_router(create_router(settings=settings, app=a, plugin=plugin, hooks=hooks))
    return TestClient(a)


def test_generate_content_no_google_api_call(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient") as mc:
        with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
            mi.return_value.evaluate = mock.AsyncMock(return_value="Result")
            r = client.post("/v1beta/models/gemini-2.5-flash:generateContent",
                            json={"contents": [{"role": "user", "parts": [{"text": "test"}]}]})
    assert r.status_code == 200
    for call in mc.call_args_list:
        assert "generativelanguage.googleapis.com" not in str(call)
```

- [ ] **Step 3: Write `test_e2e.py`** (unary static, streaming JSON-array + SSE, countTokens passthrough, timeout error)

```python
"""E2E: gemini terminal inference + passthrough."""

import json
import pytest
from unittest import mock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.gemini_frontend.proxy import create_router
from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings


@pytest.fixture
def client():
    settings = GeminiFrontendSettings(
        upstream_url="https://generativelanguage.googleapis.com",
        listen_port=9103, backend_url="http://localhost:8000", active_spec="test-spec",
    )
    plugin = mock.MagicMock()
    plugin.get_active_expression.return_value = "/echo('E2E test result')"
    plugin.resolve_context.return_value = "E2E resolved text"
    hooks = mock.MagicMock()
    hooks.emit_async = mock.AsyncMock(return_value=[])
    a = FastAPI()
    a.state.blob_store = None
    a.include_router(create_router(settings=settings, app=a, plugin=plugin, hooks=hooks))
    return TestClient(a)


def test_e2e_unary_static_spec(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient"):
        r = client.post("/v1beta/models/gemini-2.5-flash:generateContent",
                        json={"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]})
    assert r.json()["candidates"][0]["content"]["parts"][0]["text"] == "E2E resolved text"


def test_e2e_streaming_sse_format(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(return_value="SSE result")
        r = client.post("/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse",
                        json={"contents": [{"role": "user", "parts": [{"text": "SSE"}]}]})
    assert r.headers.get("content-type").startswith("text/event-stream")
    assert "data: " in r.text


def test_e2e_count_tokens_passthrough(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.httpx.AsyncClient") as mc:
        resp = mock.AsyncMock()
        resp.json.return_value = {"totalTokens": 5}
        mc.return_value.__aenter__.return_value.post.return_value = resp
        r = client.post("/v1beta/models/gemini-2.5-flash:countTokens",
                        json={"contents": [{"role": "user", "parts": [{"text": "count me"}]}]})
    assert r.json()["totalTokens"] == 5


def test_e2e_error_timeout(client):
    with mock.patch("screamingface.plugins.gemini_frontend.proxy.Url4Interpreter") as mi:
        mi.return_value.evaluate = mock.AsyncMock(side_effect=TimeoutError("Timed out after 1200s"))
        r = client.post("/v1beta/models/gemini-2.5-flash:generateContent",
                        json={"contents": [{"role": "user", "parts": [{"text": "t"}]}]})
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    assert "[url4 error]" in text and "TimeoutError" in text
```

- [ ] **Step 4: Run all gemini tests**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/gemini_frontend/tests/test_passthrough.py src/screamingface/plugins/gemini_frontend/tests/test_no_upstream_inference.py src/screamingface/plugins/gemini_frontend/tests/test_e2e.py`
Expected: all pass.

### Task 5: Migrate existing `test_proxy.py` and run C-grep for gemini settings

**Files:**
- Modify: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_proxy.py`
- Modify (if needed): `apps/server/src/screamingface/plugins/gemini_frontend/plugin.py`

- [ ] **Step 1: Confirm no `embed_*` override in gemini plugin (C)**

Run: `cd apps/server && grep -n "embed_target\|embed_mode\|system_prompt" src/screamingface/plugins/gemini_frontend/plugin.py`
Expected: no output. If present, delete the override line(s).

- [ ] **Step 2: Migrate test_proxy.py**

Keep `TestExtractLastUserText`, `TestReplaceUserText`. Delete `TestInjectSystemContext`, `TestEmbedContext` and any upstream-forward-on-inference assertions. Replace with mock-resolution synthesized-response tests.

- [ ] **Step 3: Run**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/gemini_frontend/tests/test_proxy.py`
Expected: pass.

### Task 6: M4 gate — full suite, type-check, pre-commit, commit

- [ ] **Step 1: Full gemini suite**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/gemini_frontend/tests/`
Expected: all pass.

- [ ] **Step 2: Type-check + pre-commit**

```bash
cd apps/server && uv run pyright src/screamingface/plugins/gemini_frontend/proxy.py
cd /Users/sergey/work/openmind/screamingface && pre-commit run --files apps/server/src/screamingface/plugins/gemini_frontend/proxy.py
```
Expected: 0 errors; hooks pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M4: gemini_frontend terminal rewrite (verb allow-list, JSON-array/SSE, save-less)"
```

---

## M5: ollama_frontend terminal rewrite (NDJSON)

Rewrite `proxy_chat` to resolve in-process and synthesize NDJSON using M1's `build_ollama_response` / `stream_ollama_ndjson` / `extract_error_text` / `serialize_transcript`. Keep `/api/{path}` passthrough (tags/show/pull/embeddings). Add `_save_session_if_needed`.

**Deletions:** `_inject_system_message`, `_embed_context`.
**Keep:** `_extract_last_user_text`, `/api/{path}` passthrough.

### Task 1: Failing unary terminal test

**Files:**
- Modify: `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_proxy.py`

- [ ] **Step 1: Append the test (and ensure `json`, `patch`, `httpx`, `_FakePlugin`, `_app` are imported/defined as in the file)**

```python
@pytest.mark.asyncio
async def test_unary_terminal_no_upstream_call() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434", active_spec="test-spec")
    plugin = _FakePlugin(expression="static_context_resolved_text")
    plugin.resolve_context = lambda: "The answer is 42"
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = AssertionError("Should not call upstream!")
        r = client.post("/api/chat", json={
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "What is the answer?"}],
            "stream": False,
        })
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "llama3.2"
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "The answer is 42"
    assert body["done"] is True
    assert body["done_reason"] == "stop"
    assert "eval_count" in body and "prompt_eval_count" in body
    mock_post.assert_not_called()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/ollama_frontend/tests/test_proxy.py::test_unary_terminal_no_upstream_call`
Expected: FAIL.

### Task 2: Rewrite `proxy_chat` + add `_save_session_if_needed`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/ollama_frontend/proxy.py`

- [ ] **Step 1: Add module-level `_save_session_if_needed` and `_extract_turns`**

```python
def _extract_turns(body: dict) -> list[tuple[str, str]]:
    """Extract (role, text) turns from Ollama `messages` for the $prompt blob (Decision A)."""
    turns: list[tuple[str, str]] = []
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        text = content if isinstance(content, str) else str(content)
        if text:
            turns.append((role, text))
    return turns


async def _save_session_if_needed(
    session_id: str | None,
    session_service_url: str | None,
    hooks: Any | None,
    original_user_msg: dict[str, Any] | None,
    response_body: dict[str, Any],
    streaming: bool = False,
) -> None:
    if session_id and session_service_url and hooks and original_user_msg:
        with _tracer.start_current_span("session.save_response"):
            _tracer.set_attrs({"session.id": session_id, "session.streaming": streaming})
            try:
                await hooks.emit_async(
                    "session.save_response", session_id=session_id,
                    session_service_url=session_service_url,
                    user_message_body=original_user_msg, response_body=response_body,
                )
            except Exception:
                logger.warning("Session save failed for %s", session_id, exc_info=True)
```

- [ ] **Step 2: Replace the `proxy_chat` body**

```python
@router.post("/api/chat", response_model=None, operation_id="proxy_chat")
async def proxy_chat(request: Request) -> Response:
    """Terminal inference: resolve url4 spec in-process, synthesize NDJSON response."""
    from screamingface.plugins.frontend_base.terminal_response import (
        build_ollama_response, stream_ollama_ndjson, extract_error_text, serialize_transcript,
    )

    body = await request.json()
    is_streaming = body.get("stream", True)
    model = body.get("model", "unknown")

    session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
    original_user_msg = None
    if session_id and session_service_url and hooks:
        msgs = body.get("messages", [])
        if msgs:
            original_user_msg = msgs[-1].copy() if isinstance(msgs[-1], dict) else msgs[-1]
        try:
            results = await hooks.emit_async(
                "session.enrich_request", body=body, session_id=session_id,
                session_service_url=session_service_url,
            )
            for result in results:
                if result is not None:
                    body = result
                    break
        except Exception:
            logger.warning("Session enrichment failed for %s", session_id, exc_info=True)

    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text = None
    error_dict = None
    prompt_text = ""

    try:
        if raw_expression and "$prompt" in raw_expression:
            turns = _extract_turns(body)              # Decision A
            prompt_text = serialize_transcript(turns)
            if prompt_text:
                backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None
                if backend_url:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=False) as dc:
                        blob_resp = await dc.post(
                            f"{backend_url}/data",
                            content=prompt_text.encode("utf-8"),
                            headers={"content-type": "text/plain; charset=utf-8"},
                        )
                        blob_resp.raise_for_status()
                        blob_key = blob_resp.json()["key"]
                else:
                    blob_key = request.app.state.blob_store.store(
                        prompt_text.encode("utf-8"), "text/plain; charset=utf-8"
                    )
                substituted = raw_expression.replace("$prompt", f"/data/{blob_key}")
                if backend_url:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), verify=False) as ec:
                        ens_resp = await ec.get(f"{backend_url}/ensemble", params={"q": substituted})
                        ens_resp.raise_for_status()
                        resolved_text = ens_resp.text
                else:
                    from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
                    resolved_text = await Url4Interpreter(app=request.app).evaluate(substituted)
                if not resolved_text:
                    raise RuntimeError(f"$prompt resolved to empty for spec '{settings.active_spec or 'unknown'}'")
        elif raw_expression:
            resolved_text = plugin.resolve_context() if plugin else None
            if not resolved_text:
                raise RuntimeError(f"Static spec '{settings.active_spec or 'unknown'}' resolved to empty/None")
    except Exception as exc:
        error_dict = build_ollama_response(
            extract_error_text(exc, settings.active_spec or "unknown", raw_expression or ""), model,
        )

    # Error path (fail-loud, branched on is_streaming)
    if error_dict is not None:
        error_text = error_dict["message"]["content"]
        if is_streaming:
            return StreamingResponse(stream_ollama_ndjson(error_text, model), media_type="application/x-ndjson")
        return JSONResponse(content=error_dict, status_code=200)

    # Success path
    response_dict = build_ollama_response(resolved_text or "", model, prompt_text=prompt_text)
    if is_streaming:
        await _save_session_if_needed(session_id, session_service_url, hooks, original_user_msg, response_dict, streaming=True)
        return StreamingResponse(stream_ollama_ndjson(resolved_text or "", model, prompt_text=prompt_text), media_type="application/x-ndjson")

    await _save_session_if_needed(session_id, session_service_url, hooks, original_user_msg, response_dict, streaming=False)
    return JSONResponse(content=response_dict, status_code=200)
```

- [ ] **Step 3: Delete `_inject_system_message` and `_embed_context`**

Remove both. KEEP `_extract_last_user_text` and the `/api/{path}` passthrough route.

- [ ] **Step 4: Run the unary test**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/ollama_frontend/tests/test_proxy.py::test_unary_terminal_no_upstream_call`
Expected: PASS.

### Task 3: Streaming, fail-loud, error-streaming, passthrough, $prompt tests

**Files:**
- Modify: `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_proxy.py`

- [ ] **Step 1: Append streaming NDJSON test**

```python
@pytest.mark.asyncio
async def test_streaming_terminal_ndjson_no_upstream_call() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434", active_spec="test-spec")
    plugin = _FakePlugin(expression="static_resolved")
    plugin.resolve_context = lambda: "Streaming answer here"
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.side_effect = AssertionError("Should not call upstream!")
        r = client.post("/api/chat", json={
            "model": "llama3.2",
            "messages": [{"role": "user", "content": "Stream me"}],
            "stream": True,
        })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = r.text.strip().split("\n")
    assert len(lines) >= 2
    frame1, frame2 = json.loads(lines[0]), json.loads(lines[1])
    assert frame1["message"]["content"] == "Streaming answer here" and frame1["done"] is False
    assert frame2["done"] is True and frame2["done_reason"] == "stop" and frame2["message"]["content"] == ""
    mock_stream.assert_not_called()
```

- [ ] **Step 2: Append fail-loud + error-streaming tests**

```python
@pytest.mark.asyncio
async def test_fail_loud_static_spec_none() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434", active_spec="broken-spec")
    plugin = _FakePlugin(expression="some_expression")
    plugin.resolve_context = lambda: None
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = AssertionError("Should not call upstream!")
        r = client.post("/api/chat", json={
            "model": "llama3.2", "messages": [{"role": "user", "content": "Hi"}], "stream": False,
        })
    assert r.status_code == 200
    body = r.json()
    assert "[url4 error]" in body["message"]["content"]
    assert "broken-spec" in body["message"]["content"]
    assert "empty/None" in body["message"]["content"]
    assert body["done"] is True
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_error_path_streaming_ndjson() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434", active_spec="error-spec")
    plugin = _FakePlugin(expression="failing_expression")
    plugin.resolve_context = lambda: (_ for _ in ()).throw(ValueError("Test error"))
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.side_effect = AssertionError("Should not call upstream!")
        r = client.post("/api/chat", json={
            "model": "llama3.2", "messages": [{"role": "user", "content": "Error"}], "stream": True,
        })
    assert r.status_code == 200
    lines = r.text.strip().split("\n")
    frame1, frame2 = json.loads(lines[0]), json.loads(lines[1])
    assert "[url4 error]" in frame1["message"]["content"] and "ValueError" in frame1["message"]["content"]
    assert frame1["done"] is False
    assert frame2["done"] is True and frame2["message"]["content"] == ""
    mock_stream.assert_not_called()
```

- [ ] **Step 3: Append passthrough + $prompt multi-turn tests**

```python
@pytest.mark.asyncio
async def test_api_tags_passthrough_upstream() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434")
    plugin = _FakePlugin()
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_request.return_value = httpx.Response(200, json={"models": [{"name": "llama3"}]})
        r = client.get("/api/tags")
    assert r.status_code == 200
    assert r.json()["models"][0]["name"] == "llama3"
    mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_dynamic_prompt_with_multi_turn_context() -> None:
    settings = OllamaFrontendSettings(upstream_url="http://localhost:11434", active_spec="multi-turn-spec")
    plugin = _FakePlugin(expression="/claude($prompt)")
    app = _app(settings, plugin=plugin)
    client = TestClient(app)
    stored_key = "blob_abc123"
    with patch.object(app.state, "blob_store") as mock_store:
        mock_store.store.return_value = stored_key
        with patch("screamingface.plugins.url4_executor.interpreter.Url4Interpreter.evaluate") as mock_eval:
            mock_eval.return_value = "Ensemble result text"
            r = client.post("/api/chat", json={
                "model": "llama3.2",
                "messages": [
                    {"role": "user", "content": "First question"},
                    {"role": "assistant", "content": "First answer"},
                    {"role": "user", "content": "Second question"},
                ],
                "stream": False,
            })
    assert r.status_code == 200
    assert r.json()["message"]["content"] == "Ensemble result text"
    mock_store.store.assert_called_once()
    stored_content = mock_store.store.call_args[0][0]
    # Decision A: FULL transcript is stored, so all three turns appear
    assert b"Second question" in stored_content
    assert b"First question" in stored_content
    assert b"First answer" in stored_content
    called_expr = mock_eval.call_args[0][0]
    assert f"/data/{stored_key}" in called_expr
```

> NOTE: This `$prompt` test pins Decision A — the stored blob is the FULL serialized transcript (all turns), not just the last user message. The assertion checks all three turns are present.

- [ ] **Step 4: Run all new ollama tests**

Run: `cd apps/server && uv run pytest -xvs src/screamingface/plugins/ollama_frontend/tests/test_proxy.py -k "terminal or fail_loud or error_path or tags_passthrough or multi_turn"`
Expected: all pass.

### Task 4: Migrate old forwarding tests + C-grep cleanup

**Files:**
- Modify: `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_proxy.py`

- [ ] **Step 1: Migrate/delete obsolete tests**

Delete `test_inject_system_message`/`test_inject_system_context` and any inference upstream-forward assertions. Update `test_streaming_ndjson_relay` and `test_non_streaming_passthrough_no_spec` to mock resolution and assert synthesized envelopes with `mock_post.assert_not_called()`. Keep `test_authorization_forwarded_other_stripped` (passthrough header behavior).

- [ ] **Step 2: Confirm no settings refs remain**

Run: `cd apps/server && grep -rn "embed_target\|embed_mode\|system_prompt\|_inject_system_message\|_embed_context" src/screamingface/plugins/ollama_frontend/`
Expected: no output.

- [ ] **Step 3: Full ollama suite**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/ollama_frontend/tests/`
Expected: all pass.

### Task 5: M5 gate — type-check, pre-commit, commit, no-regression

- [ ] **Step 1: Type-check + pre-commit**

```bash
cd apps/server && uv run pyright src/screamingface/plugins/ollama_frontend/proxy.py
cd /Users/sergey/work/openmind/screamingface && pre-commit run --files apps/server/src/screamingface/plugins/ollama_frontend/proxy.py apps/server/src/screamingface/plugins/ollama_frontend/tests/test_proxy.py
```
Expected: 0 errors; hooks pass.

- [ ] **Step 2: All-frontend regression**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/claude_frontend/tests/ src/screamingface/plugins/codex_frontend/tests/ src/screamingface/plugins/gemini_frontend/tests/ src/screamingface/plugins/ollama_frontend/tests/`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M5: ollama_frontend terminal rewrite (direct cutover, NDJSON, conversation-aware)"
```

---

## M6: cross-frontend tests, no-upstream integration, docs, final verification

Validate all four frontends together, prove no upstream calls on inference (and passthrough still forwards), confirm AIGateway #245 caps apply only to ensemble sub-calls, and update docs/CHANGELOG.

### Task 1: Cross-frontend integration tests

**Files:**
- Create: `apps/server/tests/test_m6_cross_frontend_integration.py`

- [ ] **Step 1: Ground the test client fixtures**

Run: `cd apps/server && grep -rn "def create_router" src/screamingface/plugins/*/proxy.py`
Use the discovered signatures to build per-frontend `TestClient` fixtures (claude/codex/gemini/ollama) with a shared mocked resolution that returns a deterministic result, mirroring the per-frontend fixtures from M2–M5.

- [ ] **Step 2: Write static-spec consistency test**

```python
"""Same active spec resolved through all four frontends returns identical text."""

import pytest


def _claude_text(resp): return resp.json()["content"][0]["text"]
def _codex_text(resp): return resp.json()["output"][0]["content"][0]["text"]
def _gemini_text(resp): return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
def _ollama_text(resp): return resp.json()["message"]["content"]


def test_static_spec_all_four_frontends_same_result(
    claude_client, codex_client, gemini_client, ollama_client
):
    # Each client fixture is wired so resolution returns "Hello from ensemble".
    claude_resp = claude_client.post("/v1/messages", json={
        "model": "claude-opus-4-1-20250805", "messages": [{"role": "user", "content": "hi"}]})
    codex_resp = codex_client.post("/v1/responses", json={"model": "gpt-4", "input": "hi"})
    gemini_resp = gemini_client.post("/v1beta/models/gemini-2.0-flash:generateContent",
                                     json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]})
    ollama_resp = ollama_client.post("/api/chat", json={
        "model": "llama2", "messages": [{"role": "user", "content": "hi"}], "stream": False})

    assert _claude_text(claude_resp) == "Hello from ensemble"
    assert _codex_text(codex_resp) == "Hello from ensemble"
    assert _gemini_text(gemini_resp) == "Hello from ensemble"
    assert _ollama_text(ollama_resp) == "Hello from ensemble"
```

- [ ] **Step 3: Write `$prompt` dynamic consistency test**

```python
def test_dynamic_prompt_spec_all_four_frontends_same_result(
    claude_client, codex_client, gemini_client, ollama_client
):
    # Resolution mock echoes the blob content + " — processed"; all four send "test input".
    claude_resp = claude_client.post("/v1/messages", json={
        "model": "claude-opus-4-1-20250805", "messages": [{"role": "user", "content": "test input"}]})
    codex_resp = codex_client.post("/v1/responses", json={"model": "gpt-4", "input": "test input"})
    gemini_resp = gemini_client.post("/v1beta/models/gemini-2.0-flash:generateContent",
                                     json={"contents": [{"role": "user", "parts": [{"text": "test input"}]}]})
    ollama_resp = ollama_client.post("/api/chat", json={
        "model": "llama2", "messages": [{"role": "user", "content": "test input"}], "stream": False})

    for resp_text in (_claude_text(claude_resp), _codex_text(codex_resp),
                      _gemini_text(gemini_resp), _ollama_text(ollama_resp)):
        assert resp_text == "test input — processed"
```

- [ ] **Step 4: Run**

Run: `cd apps/server && uv run pytest -xvs tests/test_m6_cross_frontend_integration.py`
Expected: pass.

### Task 2: Per-frontend no-upstream-on-inference tests

**Files:**
- Create: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_m6_no_upstream.py`
- Create: `apps/server/src/screamingface/plugins/codex_frontend/tests/test_m6_no_upstream.py`
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_m6_no_upstream.py`
- Create: `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_m6_no_upstream.py`

- [ ] **Step 1: Write the four files (one assertion each)**

Each: mock the resolution locus, POST the inference route, assert 200, and assert no httpx call mentions the provider host:
- claude → `api.anthropic.com`
- codex → `api.openai.com`
- gemini → `generativelanguage.googleapis.com`
- ollama → `localhost:11434`

```python
# claude example (adapt host + route per frontend)
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def test_claude_inference_no_anthropic_upstream_call():
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com", active_spec="test-spec")
    app = FastAPI(); app.include_router(create_router(settings)); client = TestClient(app)
    with patch("screamingface.plugins.frontend_base.plugin_base._fetch_sync", return_value="ok"):
        with patch("httpx.AsyncClient.post") as mp, patch("httpx.Client.post") as msp:
            r = client.post("/v1/messages", json={
                "model": "claude-opus-4-1-20250805", "messages": [{"role": "user", "content": "t"}]})
    assert r.status_code == 200
    for call in mp.call_args_list + msp.call_args_list:
        assert "api.anthropic.com" not in str(call)
```

- [ ] **Step 2: Run all four**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/*/tests/test_m6_no_upstream.py`
Expected: pass.

### Task 3: Passthrough regression tests

**Files:**
- Create: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_m6_passthrough.py`
- Create: `apps/server/src/screamingface/plugins/gemini_frontend/tests/test_m6_passthrough.py`
- Create: `apps/server/src/screamingface/plugins/ollama_frontend/tests/test_m6_passthrough.py`

- [ ] **Step 1: Write the regression tests**

- claude `POST /v1/messages/count_tokens` → forwards (catchall).
- gemini `:countTokens` and `:embedContent` → forward.
- ollama `/api/tags` (GET) and `/api/show` (POST) → forward.

Mirror the mocking style used in M2 Task 5 / M4 Task 4 / M5 Task 3 (patch the actual httpx method the route uses; assert it was called and the response relays the upstream body).

- [ ] **Step 2: Run**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_m6_passthrough.py src/screamingface/plugins/gemini_frontend/tests/test_m6_passthrough.py src/screamingface/plugins/ollama_frontend/tests/test_m6_passthrough.py`
Expected: pass.

### Task 4: AIGateway #245 sub-call grounding test

**Files:**
- Create: `apps/server/tests/test_m6_aigw_sub_calls.py`

- [ ] **Step 1: Ground the ensemble route + AIGateway middleware**

Run: `cd apps/server && grep -rn "ensemble" src/screamingface/plugins/url4_executor/ | head; grep -rn "AIGateway\|MAX_CONCURRENCY\|concurrency" src/ | grep -i aigw | head`
Document which middleware enforces the per-provider cap and which sub-routes (`/claude`, `/codex`, `/gemini`, `/ollama`) it wraps.

- [ ] **Step 2: Write the assertion test**

Write a test that drives `/ensemble` with multiple concurrent `/claude` sub-calls through a mocked AIGateway dispatch and asserts the anthropic cap (=1) is honored. If the cap is only observable via config rather than runtime in unit scope, assert the config value and document the runtime trace verification step inline as a comment.

- [ ] **Step 3: Run**

Run: `cd apps/server && uv run pytest -xvs tests/test_m6_aigw_sub_calls.py`
Expected: pass (or documented config assertion).

### Task 5: Comprehensive builder/streamer + error-path tests

**Files:**
- Create: `apps/server/tests/test_terminal_response_builders.py`
- Create: `apps/server/tests/test_terminal_response_errors.py`

- [ ] **Step 1: Builders/streamers coverage**

Cover all eight builders/streamers plus newline preservation: parse SSE on `\n\n`, NDJSON on `\n`, each frame JSON-decodes independently; assert frame order, `status:"in_progress"` (codex), stable `item_id`, monotonic `sequence_number`, camelCase Gemini `usageMetadata`, gemini JSON-array default vs `alt_sse`, ollama every-frame-`message`. Reuse the parse helpers from M1's `test_terminal_response.py`.

```python
import json
import pytest
from screamingface.plugins.frontend_base.terminal_response import (
    stream_anthropic_sse, stream_ollama_ndjson,
)


@pytest.mark.asyncio
async def test_newline_preservation_anthropic():
    chunks = [c async for c in stream_anthropic_sse("line1\nline2", "claude-3-5-sonnet")]
    text = b"".join(chunks).decode()
    assert "line1\\nline2" in text  # JSON-escaped newline survives in the delta


@pytest.mark.asyncio
async def test_newline_preservation_ollama():
    chunks = [c async for c in stream_ollama_ndjson("a\nb", "llama3.2")]
    frame1 = json.loads(b"".join(chunks).decode().strip().split("\n")[0])
    assert frame1["message"]["content"] == "a\nb"
```

- [ ] **Step 2: Error-path coverage**

Cover `extract_error_text` for httpx 502, raw interpreter exception, TimeoutError (`timed out`), and each provider's error envelope. For codex, assert error envelope uses `status="completed"` (#244 override).

```python
import httpx
from screamingface.plugins.frontend_base.terminal_response import (
    extract_error_text, build_openai_response,
)


def test_extract_error_text_httpx_502():
    req = httpx.Request("GET", "http://x/ensemble")
    exc = httpx.HTTPStatusError("502", request=req, response=httpx.Response(502, request=req))
    text = extract_error_text(exc, "spec", "/claude($prompt)")
    assert "[url4 error]" in text and "HTTPStatusError" in text


def test_build_openai_response_error_envelope_status_completed():
    env = build_openai_response("[url4 error] boom", "gpt-4o-mini", status="completed")
    assert env["status"] == "completed"  # #244 visibility override
    assert "[url4 error]" in env["output"][0]["content"][0]["text"]
```

- [ ] **Step 3: Run**

Run: `cd apps/server && uv run pytest -q tests/test_terminal_response_builders.py tests/test_terminal_response_errors.py`
Expected: pass.

### Task 6: Full server suite + type-check + pre-commit

- [ ] **Step 1: Full suite**

Run: `cd /Users/sergey/work/openmind/screamingface && (cd apps/server && uv run pytest -q tests/ src/screamingface/plugins/*/tests/)`
Expected: all pass; no upstream httpx calls on inference; passthrough routes forward.

- [ ] **Step 2: Type-check**

Run: `cd apps/server && uv run pyright src/ 2>&1 | tail -10`
Expected: 0 errors in inference handlers, `terminal_response.py`, `plugin_base.py`.

- [ ] **Step 3: Pre-commit (all files)**

Run: `cd /Users/sergey/work/openmind/screamingface && pre-commit run --all-files`
Expected: all hooks pass.

### Task 7: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `apps/server/src/screamingface/plugins/{claude,codex,gemini,ollama}_frontend/README.md` (create if missing)
- Modify: `docs/configuration.md`
- Modify: `docs/error-handling.md` (create if missing)
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: README + per-frontend READMEs**

Rename "Transparent Proxy" → "Ensemble-Terminal Frontend Proxy". State that inference routes no longer forward to real upstreams; each frontend resolves the active url4 spec (HTTP `/ensemble` or in-process `Url4Interpreter`) and synthesizes the provider-native envelope; non-inference routes still forward. Per-frontend wire formats: claude Anthropic SSE; codex OpenAI SSE; gemini JSON array (default) or SSE (`?alt=sse`); ollama NDJSON. For gemini, list the passthrough verbs (`:countTokens`, `:embedContent`, `:batchEmbedContents`, GET) vs terminal verbs (`:generateContent`, `:streamGenerateContent`). Note all four support the `$prompt` conversation-aware input fork.

- [ ] **Step 2: configuration.md (Decision C)**

Document that `embed_target`, `embed_mode`, `system_prompt` are REMOVED (hard-removed, not just deprecated). Retained: `upstream_url` (passthrough), `active_spec`, `resolve_timeout`, `session_service_url`. Note O10: static-spec resolve cache has a TTL / re-resolution and document live `active_spec`-switch behavior.

- [ ] **Step 3: error-handling.md**

Document the fake-200 error contract: timeout / 502 / in-process exception / static-spec None/empty → HTTP 200 with visible `[url4 error] ...+traceback` (never 5xx). Two resolution loci (HTTP `/ensemble` returns 502 on failure vs in-process `Url4Interpreter.evaluate()` raising directly). Blocking up to `resolve_timeout` (default 1200s). Link PR #244. State streaming errors emit a full terminating frame sequence. Call out the codex #244 override: error envelope uses `status="completed"` (NOT `status="failed"`) for CLI visibility. Note O16: a spec that does not terminate in a model backend call WARNs (does not hard-fail).

- [ ] **Step 4: CLAUDE.md "Inference Routes" section**

Add before/after table, two resolution loci, AIGateway #245 caps apply to ensemble sub-calls only, static-spec fail-loud behavior change (Decision O5b / #244), passthrough route list, and the Decision A note that the `$prompt` blob is the FULL serialized transcript.

- [ ] **Step 5: CHANGELOG.md M6 entry**

```markdown
## [M6] Cross-frontend Terminal Ensemble Rewrite (2026-06-04)

### Breaking Changes
- Static specs (no `$prompt`) that resolve to empty/None now return an error envelope (HTTP 200) instead of proceeding silently (#244, Decision O5b).
- Settings `embed_target`, `embed_mode`, `system_prompt` HARD-REMOVED from frontend settings (Decision C).

### Features
- Terminal inference for all four frontends: resolve the active url4 spec in-process (or via `/ensemble`) and synthesize provider-native envelopes; no calls to real upstreams on inference.
- Conversation-aware `$prompt`: the blob is the FULL serialized transcript (Decision A); responses echo deterministic ids + plausible non-zero usage.
- Error contract: resolution failures return HTTP 200 with visible error text + traceback (never 5xx); streaming errors emit a terminating frame. Codex error envelope uses status="completed" for CLI visibility.
- Wire-format synthesis: claude SSE (with ping); codex SSE (9-event canonical); gemini JSON array default + SSE on `?alt=sse`; ollama NDJSON.

### Non-breaking
- Non-inference passthrough unchanged: claude `count_tokens`, gemini `:countTokens`/`:embedContent`, ollama `/api/{tags,show,pull,embeddings}` still forward upstream.
- AIGateway concurrency caps (#245) still apply to ensemble sub-calls only.

### Docs
- Renamed "Transparent Proxy" → "Ensemble-Terminal Frontend Proxy"; added CLAUDE.md "Inference Routes" section, error-handling.md, configuration.md updates.
```

- [ ] **Step 6: Commit docs**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M6: cross-frontend tests, no-upstream integration, AIGW grounding, docs"
```

### Task 8: Success-criteria verification + final smoke

**Files:**
- Create (optional): `apps/server/tests/test_m6_success_criteria.py`

- [ ] **Step 1: Run the full verification gate one more time**

Run: `cd /Users/sergey/work/openmind/screamingface && (cd apps/server && uv run pytest -q tests/ src/screamingface/plugins/*/tests/) && (cd apps/server && uv run pyright src/ 2>&1 | tail -3) && pre-commit run --all-files`
Expected: all green.

- [ ] **Step 2: Manual smoke test across the four CLIs (post-commit)**

For each CLI (claude, codex, gemini, ollama): exercise static spec, `$prompt` spec, an induced resolution error (timeout), and streaming. For gemini also test `:countTokens` passthrough and both streaming formats (JSON array + `?alt=sse`); for ollama also test `/api/tags` passthrough. Confirm no real-provider errors surface (ensemble is the only upstream path) and error cases render the `[url4 error]` text in the CLI.

- [ ] **Step 3: Confirm checklist in CLAUDE.md is accurate, then final commit if anything changed**

```bash
cd /Users/sergey/work/openmind/screamingface && git add -A && git commit -m "M6: final verification + success-criteria checklist" || echo "nothing to commit"
```

---

## Adversarial-review corrections (apply during execution)

> **These corrections come from an adversarial critique run AFTER the milestone task bodies below were assembled. They are NOT yet folded into the tasks above. Where a correction conflicts with a task body, THE CORRECTION WINS.** The most important structural one: **M1 stays purely additive (new `terminal_response.py` module + tests only); the settings HARD-REMOVE and the O10/O16 code tasks are sequenced into M6 Task 0/4/5** so each milestone gate is independently green.

Checked the assembled plan against the six milestone task lists, the settled gating decisions, and ALL fourteen critic issues. Each blocker/major is fixed inline; minors addressed.

**Blockers (all fixed):**
1. **M1 C-gate fails while embed reads remain.** RESEQUENCED: Decision C hard-remove moved to **M6 Task 0**, after M2–M5 delete every `settings.embed_*` read. M6 Task 0 Step 1 greps to PROVE zero read-sites remain BEFORE removing the base fields, so the removal is atomic and runtime-safe. M1 is now purely additive (new module + test) and independently green.
2. **`system_prompt` grep over-broad.** Scoped: M6 Task 0 Step 4 greps `\bsystem_prompt\b` and explicitly EXCLUDES `*_backend_api`, `aigw_base`, `llm_base`, `interpreter_system_prompt`, `append_system_prompt`. Only `FrontendSettingsBase.system_prompt` and frontend test assignments are touched.
3. **M2 success tests incoherent (plugin=None → no resolution; wrong patch target).** Fixed: all M2 terminal tests now wire a `_static_plugin()` MagicMock whose `get_active_expression` returns a static (no-`$prompt`) spec and `resolve_context` returns the expected text — the locus the success assertions actually exercise. The `$prompt` E2E tests patch `_store_prompt_blob`/`_resolve_expression` (real $prompt locus), NOT `plugin_base._fetch_sync`. The no-spec migrated test asserts an empty synthesized envelope with no upstream call.
4. **Unused `Literal` import.** M6 Task 0 Step 2 explicitly removes `Literal` from `plugin_base.py` after deleting the two fields that used it (and from `ollama_frontend/plugin.py` if newly unused).
5. **pre-commit run from wrong dir.** ALL pre-commit invocations now run `cd apps/server && pre-commit run ...` (config lives at `apps/server/.pre-commit-config.yaml`), with a NOTE in M1 Task 3.

**Majors (all fixed):**
6. **Untracked breaking test/config sites.** M6 Task 0 Step 6 enumerates and fixes the exact files: `test_aigw_claude_e2e.py:257`, `test_proxy_context_injection.py:47`, `codex test_plugin.py:34-35`, `gemini test_proxy.py:65-66`, `claude test_claude_frontend_models.py:329`, and the ollama `plugin.py` docstring (Step 3).
7. **Codex top-level imports of deleted functions crash collection.** M3 Task 4 Step 1 now DELETES the top-level import names AND the test classes (`TestParseSSEResponse`/`TestEmbedContext`/`TestInjectSystemContext`) — no skip-stubbing.
8. **Resolve-helper signature drift / unstated embed_context removal.** M2 Task 0 greps callers (only `proxy_messages`); M2 Task 2 explicitly drops the `embed_context` callback param, adds `prompt_text`, returns the tuple, and removes embed reads in `_url4_context.py`. The orphan M1 xfail contract test was REMOVED entirely (no longer created in M1) to avoid signature-shape errors.
9. **O10 silently downgraded to docs.** Now a CODE task: **M6 Task 4** implements TTL + active-spec invalidation in `resolve_context` with two failing tests.
10. **Codex/gemini/ollama interpreter import not hoisted before red-phase patch.** Each frontend gets a **Task 0** that HOISTS `from ...interpreter import Url4Interpreter` to module scope BEFORE the red-phase tests patch `proxy.Url4Interpreter` (codex M3 T0, gemini M4 T2 S0, ollama M5 T0). The red-phase "expect fail" notes now say "assertion failure, not AttributeError."

**O16:** also promoted to a CODE task — **M6 Task 5** adds `warn_if_no_model_backend` + tests.

**Minors:**
11. **blob_store access divergence.** Standardized on `request.app.state.blob_store` across codex/gemini/ollama handlers (matching existing code).
12. **Unused fork helpers.** Decision D updated: M2/M3/M4/M5 each grep for `_extract_last_user_text`/`_replace_*` and DELETE those with no remaining caller (not "keep").
13. **AIGW #245 escape hatch.** M6 Task 4 (renumbered Task 6) decides feasibility UP FRONT in Step 1; if no runtime assertion is feasible, the task is DROPPED (not a meaningless config-constant assertion), with a CLAUDE.md note citing the middleware test.
14. **Gemini passthrough AsyncMock vs sync `resp.json()`.** All passthrough tests use `MagicMock()` response objects (via `_upstream_resp`) so `resp.json()` returns the dict synchronously, matching `proxy_gemini`'s sync `resp.json()` call.

**Type/name consistency:** M2–M5 import builders/streamers/helpers from M1's `terminal_response.py` (12 symbols) — no redefinitions. Resolve helpers consistently return `tuple[str | None, dict | None]`; `_build_error_response` returns a dict. Codex error envelope uses `status="completed"` (#244). Gemini includes `responseId` (O12). Every frontend has `_extract_turns` feeding `serialize_transcript` (Decision A), and the ollama `$prompt` test pins the FULL-transcript assertion.

**Independent-executability of M1:** M1 now touches NO existing code (new module + new test only), so its type-check/pre-commit/test gates pass standalone. The settings/contract churn that previously polluted M1 is consolidated into M6 Task 0 where its read-site dependencies are already satisfied.

---

## Self-review

Checked the assembled plan against the six milestone task lists and the settled gating decisions.

**1. Spec / decision coverage:**
- **A (conversation-aware):** Each frontend now has an `_extract_turns(body)` helper (claude M2 T3, codex M3 T1, gemini M4 T2, ollama M5 T2) feeding M1's `serialize_transcript`; the ollama `$prompt` test (M5 T3) explicitly asserts the FULL transcript (all turns) is stored. M1 builders take `prompt_text` and emit non-zero usage + deterministic ids. Covered.
- **B (passthrough):** Passthrough kept and regression-tested for claude (`count_tokens`, `/v1/models`, `/api/*`), codex (`/v1/{path}`), gemini (verb allow-list: `:countTokens`/`:embedContent`/GET/`/v1beta/{path}`), ollama (`/api/tags`, `/api/show`). M6 T3 adds dedicated regression tests. Covered.
- **C (hard-remove settings):** M1 T3–T6 remove fields from base + ollama + sf.json with a repo-wide grep gate and a dedicated removal test; gemini grep added in M4 T5. Covered.
- **D (direct cutover):** Each rewrite deletes forward/embed helpers outright with explicit delete steps; no feature flag anywhere. Covered.
- **O5b (empty = fail-loud):** Enforced in resolve helpers and inference handlers (`raise RuntimeError(... empty ...)`) and tested per frontend. Covered.
- **O10 (cache TTL / live switch):** Documented in M6 T7 configuration.md. (No code task — flagged as docs-only per the source milestone; acceptable since the source plan scoped it to documentation.)
- **O12 (gemini responseId):** Added to `build_gemini_response` (M1) and asserted in M4 T1. Covered.
- **O16 (warn on non-model spec):** Documented in M6 T7 error-handling.md. Covered as docs.
- **#244 (visibility, codex status="completed"):** M1 `build_openai_response` defaults error to `status="completed"`; codex M3 T2/T3 pass `status="completed"` and assert it; called out in docs and CHANGELOG. Covered.

**2. Placeholder scan:** Replaced the milestone drafts' `last_user_text` resolve-helper param with the conversation-aware `prompt_text` to honor Decision A, and updated the contract note. No TBD/TODO-as-implementation remain. Where a behavior depends on existing code I couldn't read (exact httpx method on catchalls, settings `extra` policy, `create_router` signatures), I added explicit grounding `grep` steps and NOTE callouts rather than guessing — these are verification steps, not placeholders.

**3. Type/name consistency:** M2–M5 import builders/streamers/helpers from M1's `terminal_response.py` (`build_anthropic_message`, `stream_anthropic_sse`, `build_openai_response`, `stream_openai_sse`, `build_gemini_response`, `stream_gemini_chunks`, `build_ollama_response`, `stream_ollama_ndjson`, `extract_error_text`, `serialize_transcript`, `estimate_tokens`, `deterministic_id`) — no redefinitions. The resolve helpers consistently return `tuple[str | None, dict | None]`. `_build_error_response` returns a dict everywhere. The M1 resolve-contract test is xfail until M2 implements the tuple, then de-xfailed in M2 T2 Step 5 (no orphan).

Reconciliations applied vs the raw milestones: (a) M2's resolve signature changed from `last_user_text` to `prompt_text` (Decision A); (b) gemini draft's `build_gemini_response` gained `responseId` (O12); (c) codex error envelope uses `status="completed"` not `"failed"` (#244); (d) ollama/codex/gemini/claude all gained `_extract_turns` for full-transcript blobs.

## Execution handoff

Plan complete. Save it to `docs/superpowers/plans/2026-06-04-frontend-terminal-ensemble-plan.md` (companion to the spec at `docs/superpowers/plans/2026-06-04-frontend-terminal-ensemble-spec.md`). Two execution options:

1. **Subagent-Driven (recommended)** — Use superpowers:subagent-driven-development: dispatch a fresh subagent per task, two-stage review between tasks, fast iteration. Best fit here because each milestone gate is independently verifiable and the grounding-grep NOTE steps benefit from a fresh-context check.

2. **Inline Execution** — Use superpowers:executing-plans: batch execution in this session with checkpoints for review at each Mn gate.

Which approach?
