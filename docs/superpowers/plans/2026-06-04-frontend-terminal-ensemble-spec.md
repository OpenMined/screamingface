# Frontend Terminal-Ensemble Reframing — Protocol Spec

## Goal / Summary

The four screamingface "frontends" — `claude_frontend`, `codex_frontend`, `gemini_frontend`, and `ollama_frontend` — are backend services that each emulate a provider's HTTP API (Anthropic Messages, OpenAI Responses, Google Gemini GenerateContent, Ollama `/api/chat`) for a CLI client. This spec reframes them so the **inference route stops proxying to the real upstream provider**. Instead, each frontend resolves the active url4 spec in-process via `/ensemble` (or the in-process `Url4Interpreter`, see §"Two resolution loci"), and returns the ensemble's reduced output wrapped in that provider's exact native response envelope (JSON unary, or a synthetic streaming frame sequence in the provider's exact wire format). All four frontends are first-class terminal endpoints; non-inference management routes continue to forward upstream unchanged. This is a request/response protocol spec.

## Locked Decisions

1. **Terminal inference route.** claude/codex/gemini/ollama frontends STOP proxying to Anthropic/OpenAI/Google/Ollama upstreams on the inference route. Each resolves the active url4 spec and RETURNS the reduced output in that provider's native envelope. No upstream provider call from the inference route.
2. **Per-spec input fork (kept).** If `active_spec` contains `$prompt`, substitute the CLI's latest user text as ensemble input; else the spec is server-predetermined and the CLI prompt is ignored. BOTH paths now terminate at the frontend. (Multi-turn history handling: see **O9**; static-spec multi-turn semantics: see **O6**.)
3. **Fake-stream.** On a streaming request, synthesize the provider's frame sequence carrying the whole result in ONE delta, in that provider's EXACT wire format:
   - **claude** = Anthropic SSE (`event:` lines, blank-line `\n\n` terminated, `ping` permitted, no `[DONE]`);
   - **codex** = OpenAI Responses SSE (blank-line `\n\n` terminated, full canonical event sequence, no `[DONE]`);
   - **gemini** = SSE iff `?alt=sse` (`data: {...}\n\n`), else a **JSON array** `[{...}]` of `GenerateContentResponse` chunks (`application/json`);
   - **ollama** = NDJSON (`application/x-ndjson`, one complete JSON object per line, NOT SSE, no `data:` prefix, no `[DONE]`).
   - Unary → JSON envelope.
4. **Error contract = PR #244 "blocking and screaming".** Block on resolution (`resolve_timeout` default 1200s); on failure (timeout / 502 / degraded `on_error=collect` / in-process interpreter exception / **static-spec resolution failure**) return a provider-shaped fake-200 whose text is the visible url4 error+traceback. Never swallow; never return HTTP 5xx to the CLI. Keep #244 negative cache + bounded/loop-aware fetch. Error rendering branches on `is_streaming` for every provider, and the streaming error path routes through the SAME frame generator as the success path so the CLI always sees a terminating frame.
5. **AIGateway concurrency cap preserved (#245, anthropic:1).** The ensemble's INTERNAL `/claude`,`/codex`,`/gemini`,`/ollama` sub-calls still hit providers via AIGateway — UNCHANGED. Only the inference route's direct proxy leg is removed.
6. **Response defaults.** Echo the request's `model`; usage zeros as a **superset of zeros** (every field each provider may require, all `0`/null — see §"Usage field shapes (pinned)"); `stop_reason=end_turn` (anthropic) / `status=completed` (openai) / `finishReason=STOP` (gemini) / `done=true, done_reason="stop"` (ollama). Response ids are freshly random per call (see **O11** for id/usage-vs-multi-turn interaction).

**Pinned helper names AND location** (resolving O3): all eight builders/streamers live EXCLUSIVELY in the shared module `frontend_base/terminal_response.py`. Per-frontend modules, if any, import and re-export only — they MUST NOT replicate wire-format logic.
- claude: `build_anthropic_message(result, model)` / `stream_anthropic_sse(result, model)`
- codex: `build_openai_response(result, model)` / `stream_openai_sse(result, model)`
- gemini: `build_gemini_response(result, model)` / `stream_gemini_chunks(result, model, alt_sse=False)`
- ollama: `build_ollama_response(result, model)` / `stream_ollama_ndjson(result, model)`

**Formal signatures (pinned):**

```python
def build_anthropic_message(result_text: str, model: str) -> dict: ...
async def stream_anthropic_sse(result_text: str, model: str) -> AsyncIterator[bytes]: ...
def build_openai_response(result_text: str, model: str) -> dict: ...
async def stream_openai_sse(result_text: str, model: str) -> AsyncIterator[bytes]: ...
def build_gemini_response(result_text: str, model: str) -> dict: ...
async def stream_gemini_chunks(result_text: str, model: str, alt_sse: bool = False) -> AsyncIterator[bytes]: ...
def build_ollama_response(result_text: str, model: str) -> dict: ...
async def stream_ollama_ndjson(result_text: str, model: str) -> AsyncIterator[bytes]: ...
```

---

## Two resolution loci (in-process interpreter vs HTTP `/ensemble`)

Resolution happens via **one of two loci**, and the error contract MUST cover both:

1. **HTTP `/ensemble`** (`url4_executor/routes.py`): GET resolves and returns `PlainTextResponse`; on evaluation failure it raises `HTTPException(status_code=502, detail="url4 evaluation failed: ...")` (routes.py:132). The frontend's `_fetch`/`_fetch_sync` GET this route and `raise_for_status()`.
2. **In-process `Url4Interpreter`** (when the app exposes a blob store; the common in-process case): the frontend calls `Url4Interpreter(app).evaluate(...)` directly — **no** HTTP, **no** 502 wrapping. Exceptions are raw interpreter exceptions.

Because exception types differ between loci, the error contract is defined in terms of **"any exception raised during resolution"**, not "`/ensemble` returns 502". `extract_error_text()` MUST format both an httpx `HTTPStatusError` (502 path) and a raw `Url4Interpreter` exception uniformly. Flows below say "Resolve spec" to mean "via whichever locus applies."

---

## Architecture: Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| **Upstream call on inference** | Yes, always | No, never |
| **URL4 resolution** | Yes, embedded into request body, then forwarded | Yes, result becomes the response text |
| **Error handling** | HTTP 5xx/4xx from upstream | HTTP 200 fake-envelope with error text + traceback |
| **Static-spec resolution failure** | Swallowed (returns None, request proceeds, full history still forwarded) | Fail-loud: error envelope returned (see **decision below**) |
| **Response format** | Pass-through from upstream | Synthesized by `build_<provider>_*()` |
| **Streaming** | Pass-through from upstream | Synthesized single-delta frame sequence in exact wire format |
| **Model field** | From upstream response | Echoed from request |
| **Usage fields** | From upstream response | Superset of zeros (full per-provider field set) |
| **Non-inference routes** | Forward upstream | Forward upstream (UNCHANGED) |
| **AIGateway concurrency caps** | Apply to `/ensemble` fan-out only | Apply to `/ensemble` fan-out only (UNCHANGED) |

The context-embedding machinery (`_embed_context`, `_inject_system_context`/`_inject_system_message`) is deleted from every inference path: there is no outbound request body to mutate, so the resolved text goes **directly into the response envelope**, not into a forwarded request.

**Static-spec fail-loud (resolves a contradiction).** Today `FrontendPluginBase.resolve_context()` (plugin_base.py:279–283) **catches** per-spec resolution exceptions, logs a warning, and returns `None` (so a failed static spec proceeds with no context). Under the terminal rewrite a `None`/empty static result would otherwise produce a blank HTTP 200 — silently violating the #244 contract. **Decision:** the inference handler treats a `None`/empty resolved value for a non-`$prompt` spec **as a resolution failure** and returns the provider error envelope. Implementation: either (a) the per-provider static resolver re-raises so the handler's `except` fires, or (b) the handler explicitly checks `resolved_text` is non-empty when `raw_expression` is set and synthesizes the error envelope otherwise. This is a deliberate behavior change from the current non-fatal swallow and MUST be called out in the changelog. (Empty-result-vs-error nuance for the `$prompt` path: see **O5b**.)

---

## Usage field shapes (pinned, supersets-of-zeros)

Per Locked Decision #6, every provider emits the **superset** of usage fields it may require, all zero/null. The Anthropic `Usage` model is `extra="allow"` (models.py:134), and codex/gemini consumers ignore unknown zero fields, so supersets are safe everywhere. This resolves O1 (claude minimal-vs-extended) in favor of the superset.

- **claude** (`usage`, message_start + unary + `message_delta`):
  `{"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}`
  (In `message_delta`, emit `{"output_tokens": 0}` only, per the Anthropic wire convention.)
- **codex** (`usage`): `{"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}`
- **gemini** (`usageMetadata`, camelCase): `{"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}`
- **ollama**: duration/eval fields — `{"total_duration": 0, "load_duration": 0, "prompt_eval_count": 0, "prompt_eval_duration": 0, "eval_count": 0, "eval_duration": 0}`

---

## Query / Request / Response Flow

### Flow 1 — `$prompt`-dynamic turn (AFTER)

```
CLI Request: POST /v1/messages (or /v1/responses, /v1beta/...:generateContent, /api/chat)
    │
    └─→ [Frontend Inference Handler]
         │
         ├─→ Session enrichment (if enabled)
         │
         ├─→ Detect $prompt in active spec
         │    └─→ Extract input text (see O9 for last-turn-only vs full transcript)
         │    └─→ Store input as blob (/data/{key})
         │    └─→ Substitute $prompt → /data/{key} in expression
         │    └─→ Resolve via HTTP /ensemble OR in-process Url4Interpreter
         │         (ensemble sub-calls /claude,/codex,/gemini,/ollama → AIGateway → real upstreams,
         │          subject to per-provider concurrency caps)
         │    └─→ Reducer collects responses → final resolved text
         │
         ├─→ NO forward to real upstream
         │
         ├─→ Build provider-native envelope from resolved text
         │    ├─→ is_streaming=true → synthesize provider's exact frame sequence (Decision #3)
         │    └─→ is_streaming=false → single JSON response object
         │
         ├─→ session.save(<builder dict>) once (see O7; same dict for unary & streaming)
         │
         └─→ Return provider-shaped response → CLI

   NO UPSTREAM CALL on inference route.
   Response Source: in-process ensemble result.
```

### Flow 2 — Static (no `$prompt`) turn (AFTER)

```
CLI Request: POST /v1/messages (active static spec, no $prompt)
    │
    └─→ [Frontend Inference Handler]
         │
         ├─→ Resolve static spec → cached resolved text (resolve_context())
         │    └─→ If resolution fails OR yields None/empty → ERROR ENVELOPE (fail-loud; see §Static-spec fail-loud)
         │
         ├─→ Build provider-native envelope from resolved text
         │
         ├─→ session.save(<builder dict>) once
         │
         └─→ Return provider-shaped response → CLI

   NO upstream call on inference route.
   Static context is resolved at startup/first-request and cached (per spec name, process lifetime — see O10).
   The CLI prompt is ignored (see O6 for multi-turn semantics).
```

### Flow 3 — Error flow (timeout / 502 / collected errors / in-process exception / static None)

```
CLI Request: POST <inference route>
    │
    └─→ [Frontend Inference Handler]
         │
         ├─→ Session enrichment
         ├─→ URL4 resolution ($prompt or static), via either locus
         │    │
         │    └─ Any of: TimeoutError; /ensemble 502 (HTTPStatusError);
         │       in-process Url4Interpreter exception; on_error=collect insufficient;
         │       static spec resolves to None/empty
         │       → Exception captured (or None-as-failure synthesized)
         │
         ├─→ extract_error_text(exc, spec_name, expression) → structured text+traceback
         │
         ├─→ Build ERROR envelope (fake-200, provider-shaped):
         │    ├─→ is_streaming=true:
         │    │    └─→ route the error text through the SAME success frame generator
         │    │        (stream_<provider>_sse/ndjson) so a terminating frame is always sent
         │    └─→ is_streaming=false:
         │         └─→ single JSON error object with full error text in content
         │
         └─→ HTTP 200 provider-shaped fake response → CLI  (never HTTP 5xx)
```

**Streaming error helper contract (all four).** There is no separate "error streamer." The streaming error path extracts the error text and feeds it to the normal `stream_<provider>_*(error_text, model)` generator, guaranteeing the full terminating frame set. This also fixes a pre-existing bug: today a **streaming** request that hits a `$prompt` resolution error returns a **unary** `JSONResponse` (claude proxy.py:213–224; codex:299; gemini:250/269; ollama:260/283), which streaming clients mishandle. After the rewrite, the handler branches on `is_streaming` before emitting the error.

---

## Component Spec: claude_frontend

**Plugin path:** `apps/server/src/screamingface/plugins/claude_frontend/`
**Inference route:** `POST /v1/messages`
**Emulates:** Anthropic Messages API.

### Current flow (before terminal rewrite)

`proxy_messages` (`/v1/messages`) is a three-stage handler: (1) session enrichment; (2) URL4 context injection (`$prompt` via `resolve_prompt_expression()` or static via `resolve_static_context()`, each calling `embed_context()` and short-circuiting to a fake-200 error envelope via `_build_error_response()`); (3) forward to Anthropic via `_forward_streaming()` (402–474) / `_forward_unary()` (477–515). Helpers: `_embed_context` (136–153), `_inject_system_context` (126–133), `_extract_last_user_text` (72–96), `_replace_last_user_message` (99–123); `_url4_context.py`: `resolve_prompt_expression` (190–282), `resolve_static_context` (284–314), `_build_error_response` (47–84).

### Resolve-helper contract change (resolves the ambiguity blocker)

The resolve helpers change from "mutate `body`, return `JSONResponse | None`" to an explicit two-channel result. **Pinned shape:**

```python
# _url4_context.py — new signatures
async def resolve_prompt_expression(...) -> tuple[str | None, JSONResponse | None]:
    """Returns (resolved_text, None) on success, or (None, error_envelope_or_dict) on failure.
    No longer calls embed_context(); no body mutation."""

def resolve_static_context(...) -> tuple[str | None, JSONResponse | None]:
    """Returns (resolved_text, None) on success. On failure OR None/empty result,
    returns (None, error_response). Re-raises into the tuple's error channel rather
    than swallowing (reverses the plugin_base swallow for the inference path)."""
```

The error channel carries the **envelope dict** (not a prebuilt `JSONResponse`) so the handler can render unary vs SSE. `_build_error_response()` is refactored to **return the envelope dict**; the handler wraps it in `JSONResponse` (unary) or feeds `content[0].text` to `stream_anthropic_sse` (streaming).

### Terminal rewrite — new inference handler

```python
@router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
async def proxy_messages(request: Request) -> Response:
    body = await request.json()
    is_streaming = body.get("stream", False)
    model = body.get("model", "claude-opus-4-1-20250805")

    # Stage 1: Session enrichment (unchanged)
    session = SessionHook.from_request(...)
    body = await session.enrich(body, tracer=_tracer)

    # Stage 2: URL4 resolution → terminal
    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text, error_dict = None, None
    if raw_expression and "$prompt" in raw_expression:
        resolved_text, error_dict = await resolve_prompt_expression(body, ...)
    elif raw_expression:
        resolved_text, error_dict = resolve_static_context(...)

    # Stage 3: Error path (branched on is_streaming)
    if error_dict is not None:
        error_text = error_dict["content"][0]["text"]
        if is_streaming:
            return StreamingResponse(stream_anthropic_sse(error_text, model),
                                     media_type="text/event-stream")
        return JSONResponse(content=error_dict)

    # Stage 4: Success
    if is_streaming:
        async def gen():
            async for chunk in stream_anthropic_sse(resolved_text, model):
                yield chunk
        # session.save receives the SAME dict the streamer encodes (not re-parsed frames)
        await session.save(build_anthropic_message(resolved_text, model),
                           streaming=True, tracer=_tracer)
        return StreamingResponse(gen(), media_type="text/event-stream")

    response_dict = build_anthropic_message(resolved_text, model)
    await session.save(response_dict, streaming=False, tracer=_tracer)
    return JSONResponse(content=response_dict)
```

**Deleted (`proxy.py`):** `_forward_streaming()` (402–474), `_forward_unary()` (477–515), `_inject_system_context()` (126–133), `_embed_context()` (136–153), upstream URL construction (240–244).

**KEEP:** `_extract_last_user_text()`, `_replace_last_user_message()` (input fork). `/v1/{path}` and `/api/{path}` passthroughs (see Non-inference table).

### Non-streaming envelope — `build_anthropic_message(result, model)`

```json
{
  "id": "msg_<random_hex>",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "<result_string>"}],
  "model": "<model_param>",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

### Synthetic SSE — `stream_anthropic_sse(result, model)`

Exact wire format: `event:` lines, **blank-line (`\n\n`) terminated**, with at least one `ping` after `message_start`, no `[DONE]`. Frame order:
`message_start` → `ping` → `content_block_start` → `content_block_delta` (whole text in ONE delta) → `content_block_stop` → `message_delta` → `message_stop`.

```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_a1b2c3d4e5f6", "type": "message", "role": "assistant", "content": [], "model": "claude-opus-4-1-20250805", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}

event: ping
data: {"type": "ping"}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "User-agent: *\nDisallow: /"}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 0}}

event: message_stop
data: {"type": "message_stop"}
```

```python
async def stream_anthropic_sse(result: str, model: str) -> AsyncIterator[bytes]:
    import json, uuid
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"

    def sse(event_name: str, payload: dict) -> bytes:
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    yield sse("message_start", {"type": "message_start", "message": {
        "id": msg_id, "type": "message", "role": "assistant", "content": [],
        "model": model, "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})
    yield sse("ping", {"type": "ping"})
    yield sse("content_block_start", {"type": "content_block_start", "index": 0,
              "content_block": {"type": "text", "text": ""}})
    yield sse("content_block_delta", {"type": "content_block_delta", "index": 0,
              "delta": {"type": "text_delta", "text": result}})
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield sse("message_delta", {"type": "message_delta",
              "delta": {"stop_reason": "end_turn", "stop_sequence": None},
              "usage": {"output_tokens": 0}})
    yield sse("message_stop", {"type": "message_stop"})
```

The same generator renders the error path (the error text becomes the single `content_block_delta`), so the CLI always receives a terminating `message_stop`.

### Error envelope (`build_anthropic_message`-shaped, fake-200)

```json
{
  "id": "sf_error_<hex>",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "[url4 error] <spec_name>\n\nExpression: <truncated>\n\nError: <exc_type>: <exc_msg>\n\nTraceback:\n<full_tb>"}],
  "model": "<model_from_body>",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
}
```

---

## Component Spec: codex_frontend

**Plugin:** `codex-frontend`
**Plugin path:** `apps/server/src/screamingface/plugins/codex_frontend/`
**Inference route:** `POST /v1/responses`
**Emulates:** OpenAI Responses API.

### Current flow (before terminal rewrite)

`proxy_responses(request)` (`proxy.py:210–418`): session enrichment; URL4 injection (`$prompt` 236–299 / static 300–324, both via `_embed_context`); upstream forward (streaming + non-streaming, 327–418) with `_parse_sse_response` (117–178) to reconstruct for session save; `/v1/{path}` catchall (420–450). `_inject_system_context` (89–95), `_embed_context` (98–114) are dead after rewrite.

### Terminal rewrite — new handler

```python
async def proxy_responses(request: Request) -> Response:
    body = await request.json()
    is_streaming = body.get("stream", False)
    model = body.get("model", "unknown")

    session_id = extract_session_id(request)
    enrich_body_from_hooks(body, session_id)

    raw_expression = plugin.get_active_expression()
    resolved_text, exc = None, None
    try:
        if raw_expression and "$prompt" in raw_expression:
            blob_key = store_blob(extract_last_user_text(body))
            substituted = raw_expression.replace("$prompt", f"/data/{blob_key}")
            resolved_text = await resolve(substituted)         # /ensemble or in-process
        elif raw_expression:
            resolved_text = plugin.resolve_context()
            if resolved_text is None or resolved_text == "":
                raise RuntimeError("static spec resolved to empty (fail-loud)")
    except Exception as e:
        exc = e

    if exc is not None:
        error_text = extract_error_text(exc, spec_name, raw_expression or "")
        if is_streaming:
            return StreamingResponse(stream_openai_sse(error_text, model, status="failed"),
                                     media_type="text/event-stream")
        return JSONResponse(content=build_openai_response(error_text, model, status="failed"),
                            status_code=200)

    if is_streaming:
        await hooks_save(session_id, build_openai_response(resolved_text, model))  # same dict, not re-parsed
        return StreamingResponse(stream_openai_sse(resolved_text, model),
                                 media_type="text/event-stream")
    response_dict = build_openai_response(resolved_text, model)
    await hooks_save(session_id, response_dict)
    return JSONResponse(content=response_dict, status_code=200)
```

`build_openai_response`/`stream_openai_sse` take an optional `status="completed"` param; the error path passes `status="failed"`.

### Non-streaming envelope — `build_openai_response(result, model, status="completed")`

Adds `created_at` (required int unix timestamp — fixes the decode-error blocker) and a full output item with `id`, `status`, and `content`:

```python
def build_openai_response(result: str, model: str, status: str = "completed") -> dict[str, Any]:
    import uuid, time
    resp_id = f"resp_{uuid.uuid4().hex[:12]}"
    item_id = f"msg_{uuid.uuid4().hex[:12]}"
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "status": status,                       # "completed" or "failed"
        "output": [
            {
                "id": item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        },
    }
```

### Synthetic SSE — `stream_openai_sse(result, model, status="completed")`

**Fixes (blockers/majors):** blank-line `\n\n` framing; the full canonical Responses event sequence including `content_part.added/.done` and `output_text.done`; `status="in_progress"` (not `"processing"`); stable `item_id` across all item/part/delta/done events; `created_at`; `sequence_number`, `output_index`, `content_index` on the relevant events; no `[DONE]`.

Event order (one delta carrying the entire text):
`response.created` → `response.in_progress` → `response.output_item.added` → `response.content_part.added` → `response.output_text.delta` → `response.output_text.done` → `response.content_part.done` → `response.output_item.done` → `response.completed`.

```python
async def stream_openai_sse(result: str, model: str, status: str = "completed") -> AsyncIterator[bytes]:
    import json, uuid, time
    resp_id = f"resp_{uuid.uuid4().hex[:12]}"
    item_id = f"msg_{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    seq = 0

    def event(payload: dict) -> bytes:
        nonlocal seq
        payload.setdefault("sequence_number", seq)
        seq += 1
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    base_resp = {"id": resp_id, "object": "response", "created_at": created,
                 "model": model, "output": [], "usage": None}

    yield event({"type": "response.created",
                 "response": {**base_resp, "status": "in_progress"}})
    yield event({"type": "response.in_progress",
                 "response": {**base_resp, "status": "in_progress"}})
    yield event({"type": "response.output_item.added", "output_index": 0,
                 "item": {"id": item_id, "type": "message", "status": "in_progress",
                          "role": "assistant", "content": []}})
    yield event({"type": "response.content_part.added", "item_id": item_id,
                 "output_index": 0, "content_index": 0,
                 "part": {"type": "output_text", "text": "", "annotations": []}})
    yield event({"type": "response.output_text.delta", "item_id": item_id,
                 "output_index": 0, "content_index": 0, "delta": result})
    yield event({"type": "response.output_text.done", "item_id": item_id,
                 "output_index": 0, "content_index": 0, "text": result})
    yield event({"type": "response.content_part.done", "item_id": item_id,
                 "output_index": 0, "content_index": 0,
                 "part": {"type": "output_text", "text": result, "annotations": []}})
    yield event({"type": "response.output_item.done", "output_index": 0,
                 "item": {"id": item_id, "type": "message", "status": "completed",
                          "role": "assistant",
                          "content": [{"type": "output_text", "text": result, "annotations": []}]}})
    yield event({"type": "response.completed",
                 "response": {**base_resp, "status": status,
                              "output": [{"id": item_id, "type": "message", "status": "completed",
                                          "role": "assistant",
                                          "content": [{"type": "output_text", "text": result,
                                                       "annotations": []}]}],
                              "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                                        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})
```

Validate against the codebase's `codex_backend_api/sse_parser.py` AND a real Codex CLI smoke test.

### Error envelope (`status:"failed"`, HTTP 200) — full schema

Identical structure to `build_openai_response` with `status="failed"` and the error text in `output[0].content[0].text`:

```json
{
  "id": "sf_error_<hex>",
  "object": "response",
  "created_at": 1750000000,
  "model": "<model>",
  "status": "failed",
  "output": [
    {
      "id": "msg_<hex>",
      "type": "message",
      "status": "completed",
      "role": "assistant",
      "content": [{"type": "output_text", "text": "[url4 error] <ClassName>: <message>\n\nExpression: <truncated>\n\nTraceback:\n...", "annotations": []}]
    }
  ],
  "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
}
```

### Deletions / retained (`codex_frontend/proxy.py`)

- DELETE: `_inject_system_context()` (89–95), `_embed_context()` (98–114), `_parse_sse_response()` (117–178, no upstream stream to parse), `$prompt` path (236–299), static path (300–324), upstream forwarding + post-upstream save (327–418).
- KEEP: `_extract_last_user_text()` (50–69), `_replace_user_text()` (72–86), `_build_headers()` (198–208, catchall only), `/v1/{path}` catchall.

---

## Component Spec: gemini_frontend

**Plugin path:** `apps/server/src/screamingface/plugins/gemini_frontend/`
**Inference verbs:** `POST .../{model}:generateContent` (unary), `POST .../{model}:streamGenerateContent` (streaming).
**Passthrough verbs (CRITICAL):** `:countTokens`, `:embedContent`, `:batchEmbedContents`, any other `:`-suffixed POST verb, and all GET — these MUST forward upstream.
**Emulates:** Google Gemini API.

### Single-route verb disambiguation (fixes the route blocker)

Ground truth: there is ONE handler `proxy_gemini(request, model_path)` bound to `/v1beta/models/{model_path:path}` (proxy.py:140–146). The `{model_path:path}` capture swallows the verb suffix (`:countTokens`, `:embedContent`, `:generateContent`, `:streamGenerateContent`) — ALL of these hit `proxy_gemini`, NOT the `/v1beta/{path}` catchall. Therefore the handler MUST itself branch:

```python
async def proxy_gemini(request: Request, model_path: str) -> Response:
    is_inference = model_path.endswith(":generateContent") or model_path.endswith(":streamGenerateContent")
    if request.method == "GET" or not is_inference:
        # Passthrough: model metadata, :countTokens, :embedContent, :batchEmbedContents, etc.
        return await forward_upstream(request, f"{upstream_url}/v1beta/models/{model_path}")

    # Inference path (terminal)
    is_streaming = model_path.endswith(":streamGenerateContent")
    body = await request.json()
    model = model_path.split(":")[0].split("/")[-1]
    # session enrich (unchanged) ...
    # resolve ($prompt or static, fail-loud on None/empty static) ...
    if is_streaming:
        alt_sse = "alt=sse" in str(request.url.query)
        return StreamingResponse(
            stream_gemini_chunks(resolved_text, model, alt_sse=alt_sse),
            media_type="text/event-stream" if alt_sse else "application/json",
        )
    return JSONResponse(content=build_gemini_response(resolved_text, model), status_code=200)
```

**Allow-list is explicit:** only `:generateContent`/`:streamGenerateContent` terminate; everything else forwards upstream from inside `proxy_gemini`. A `:countTokens` request returns a real token count (forwarded), NOT a synthesized text answer. Add a regression test asserting `:countTokens` forwards upstream.

### Non-streaming envelope — `build_gemini_response(result, model)`

```json
{
  "candidates": [
    {
      "content": {"role": "model", "parts": [{"text": "<result>"}]},
      "finishReason": "STOP",
      "index": 0,
      "safetyRatings": []
    }
  ],
  "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0},
  "modelVersion": "<model>"
}
```

camelCase `usageMetadata` is authoritative (resolves O1 for gemini). `modelVersion` is included (cheap, matches real output); `responseId` may be added if a CLI requires it (see **O12**).

```python
def build_gemini_response(result: str, model: str) -> dict:
    return {
        "candidates": [{
            "content": {"role": "model", "parts": [{"text": result}]},
            "finishReason": "STOP", "index": 0, "safetyRatings": []
        }],
        "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0},
        "modelVersion": model,
    }
```

### Streaming — `stream_gemini_chunks(result, model, alt_sse=False)`

**Resolves O4 in favor of the JSON ARRAY default** (matching Google's real `streamGenerateContent` REST wire format; fixes the body/Content-Type contradiction blocker).

- **`?alt=sse`** → `text/event-stream`, `data: <obj>\n\n`, no `[DONE]`:
  ```
  data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "<result>"}]}, "finishReason": "STOP", "index": 0, "safetyRatings": []}], "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}, "modelVersion": "<model>"}

  ```
- **default (no `?alt=sse`)** → `application/json`, a true JSON ARRAY `[ <obj> ]`:
  ```
  [{"candidates": [{"content": {"role": "model", "parts": [{"text": "<result>"}]}, "finishReason": "STOP", "index": 0, "safetyRatings": []}], "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}, "modelVersion": "<model>"}]
  ```

```python
async def stream_gemini_chunks(result: str, model: str, alt_sse: bool = False) -> AsyncIterator[bytes]:
    import json
    obj = build_gemini_response(result, model)
    if alt_sse:
        yield f"data: {json.dumps(obj)}\n\n".encode("utf-8")
    else:
        # JSON array framing so application/json is honest
        yield b"["
        yield json.dumps(obj).encode("utf-8")
        yield b"]"
```

The same generator renders the streaming error path (error text as the single chunk's `parts[0].text`, `finishReason: STOP`).

### Error envelope (fake-200)

```json
{
  "candidates": [
    {
      "content": {"role": "model", "parts": [{"text": "[url4 error] TimeoutError: Spec resolution timed out after 1200.0s\n\nTraceback:\n..."}]},
      "finishReason": "STOP",
      "index": 0,
      "safetyRatings": []
    }
  ],
  "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0},
  "modelVersion": "<model>"
}
```

On streaming, emit a single error chunk in the negotiated format (SSE `data: {...}\n\n` iff `?alt=sse`, else `[ {...} ]`).

### Session save (explicit decision — fixes the asymmetry major)

Ground truth: gemini's inference path **enriches** (`session.enrich_request`, proxy.py:171) but has **NO** `save_response` today. **Decision:** gemini remains **save-less** in this work — it keeps `enrich_request` and gains NO new save. The shared-changes table and test matrix below reflect this: **no gemini session-persistence tests**. (Adding save to gemini is explicitly out of scope; tracked as **O7b** if desired later.)

### Deletions / retained (`gemini_frontend/proxy.py`)

- DELETE: `_embed_context()` (93–109), `_inject_system_context()` (83–91), upstream-forward block on the inference branch (282–310).
- REPURPOSE: `$prompt` block (191–231) and static block (251–271) — drop the `_embed_context()` call; `resolved_text` flows into the builders; static None/empty → fail-loud error envelope.
- KEEP: verb-disambiguation passthrough (GET + non-generate POST verbs → upstream), `_build_headers()` (128–138), session enrichment (167–187), `/v1beta/{path}` catchall (318–342).
- `_extract_last_user_text()`, `_replace_user_text()` retained for the input fork.

---

## Component Spec: ollama_frontend

**Status:** FIRST-CLASS IN SCOPE. Backend service emulating the Ollama HTTP API.
**Plugin path:** `apps/server/src/screamingface/plugins/ollama_frontend/`
**Inference route:** `POST /api/chat`
**Streaming wire format:** **NDJSON (`application/x-ndjson`) — NOT SSE.** One complete JSON object per line, no `data:` prefix, no blank-line separators, no `[DONE]`.

### Current flow (status quo)

`proxy_chat(request)` parses JSON, runs session enrichment + url4 resolution, `_embed_context()` into the body, forwards to upstream Ollama (`client.stream` :342 NDJSON relay; `client.post` :407/:415 unary). Injection paths: static (261–291) and dynamic `$prompt` (164–260). Embedding helpers: `_inject_system_message` (67–82), `_extract_last_user_text` (47–56), `_embed_context` (84–103). `_ndjson.parse_ndjson_response()` reconstructs for session save.

### Terminal rewrite — ensemble-first inference

```python
async def proxy_chat(request: Request) -> Response:
    body = await request.json()
    is_streaming = body.get("stream", True)   # Ollama defaults stream=true
    model = body.get("model", "unknown")

    # 1. Session enrichment (unchanged)
    # 2. Resolve spec → string
    raw_expression = plugin.get_active_expression() if plugin else None
    resolved_text, exc = None, None
    try:
        if raw_expression and "$prompt" in raw_expression:
            resolved_text = await _resolve_prompt_expression(...)   # /ensemble or in-process
        elif raw_expression:
            resolved_text = plugin.resolve_context()
            if resolved_text is None or resolved_text == "":
                raise RuntimeError("static spec resolved to empty (fail-loud)")
    except Exception as e:
        exc = e

    # 3. Error path
    if exc is not None:
        error_text = extract_error_text(exc, spec_name, raw_expression or "")
        if is_streaming:
            return StreamingResponse(stream_ollama_ndjson(error_text, model),
                                     media_type="application/x-ndjson")
        return JSONResponse(content=build_ollama_response(error_text, model))

    # 4. Success
    if is_streaming:
        # session.save receives the same dict the streamer encodes (not re-parsed frames)
        await _save_session(build_ollama_response(resolved_text, model))
        return StreamingResponse(stream_ollama_ndjson(resolved_text, model),
                                 media_type="application/x-ndjson")
    response_dict = build_ollama_response(resolved_text, model)
    await _save_session(response_dict)
    return JSONResponse(content=response_dict)
```

The error path reuses `stream_ollama_ndjson`/`build_ollama_response` with the error text as `message.content` — no abbreviated frames.

### Non-streaming envelope — `build_ollama_response(result, model)`

```json
{
  "model": "<model>",
  "created_at": "2025-06-04T00:00:00Z",
  "message": {"role": "assistant", "content": "<result>"},
  "done": true,
  "done_reason": "stop",
  "total_duration": 0,
  "load_duration": 0,
  "prompt_eval_count": 0,
  "prompt_eval_duration": 0,
  "eval_count": 0,
  "eval_duration": 0
}
```

### Streaming — `stream_ollama_ndjson(result, model)` (NDJSON, not SSE)

Two complete NDJSON objects, **each structurally complete** (every frame, including the terminal `done` frame, carries a `message` field — fixes the abbreviated-frame major). The whole resolved text rides in the first frame's `message.content`; the terminal frame has empty content and `done:true`.

```
{"model":"<model>","created_at":"2025-06-04T00:00:00Z","message":{"role":"assistant","content":"<result>"},"done":false}
{"model":"<model>","created_at":"2025-06-04T00:00:00Z","message":{"role":"assistant","content":""},"done":true,"done_reason":"stop","total_duration":0,"load_duration":0,"prompt_eval_count":0,"prompt_eval_duration":0,"eval_count":0,"eval_duration":0}
```

```python
async def stream_ollama_ndjson(result: str, model: str) -> AsyncIterator[bytes]:
    import json
    created = "2025-06-04T00:00:00Z"
    yield (json.dumps({
        "model": model, "created_at": created,
        "message": {"role": "assistant", "content": result},
        "done": False,
    }) + "\n").encode("utf-8")
    yield (json.dumps({
        "model": model, "created_at": created,
        "message": {"role": "assistant", "content": ""},
        "done": True, "done_reason": "stop",
        "total_duration": 0, "load_duration": 0, "prompt_eval_count": 0,
        "prompt_eval_duration": 0, "eval_count": 0, "eval_duration": 0,
    }) + "\n").encode("utf-8")
```

> **Note (simplification, intentional):** real Ollama emits one NDJSON object per model chunk; this synthesizes the whole result in a single content frame plus a terminal `done` frame. The Ollama python/JS clients and `ollama run` accumulate `message.content` across frames and stop on `done:true`, so the single-content-frame form is accepted. Every frame is a complete JSON object on its own line; this is NOT SSE.

### Error envelope (fake-200)

`build_ollama_response(error_text, model)` (unary) and `stream_ollama_ndjson(error_text, model)` (streaming) — the error text rides in `message.content`; the terminal frame still carries a complete `message` field.

### Deleted vs retained (`ollama_frontend/proxy.py`)

- DELETE: `_embed_context()` (84–103), `_inject_system_message()` (67–82), upstream forward paths (`client.stream` :342, `client.post` :407/:415, URL/header build :304–313), session save on upstream response (363–391, 423–441 — replaced with save on the builder dict). Remove the `embed_target` default override (settings line 37).
- KEEP: session enrichment hooks, tracer, `/api/{path}` passthrough (446–453), header forwarding, `_build_headers()` (116–127). `_extract_last_user_text()` retained for the `$prompt` input fork. `_ndjson.parse_ndjson_response()` is no longer needed on the inference path (save receives the builder dict directly) but is retained if used elsewhere.

### Non-inference passthrough: `/api/{path}` (`proxy_passthrough()` :446–453)

`GET /api/tags`, `GET /api/show`, `POST /api/pull`, `POST /api/embeddings` forward unchanged to `upstream_url/api/{path}`. **Model-existence divergence (documented, see O13):** synthesized `/api/chat` answers for a model that the upstream Ollama server may not host, while passthrough `/api/show`/`/api/tags` reflect the real upstream. Clients that gate chat on a successful `/api/show` may see an inconsistency. NOT in scope for the ensemble refactor.

---

## Component Spec: shared base & terminal_response module

**Base classes:** `FrontendPluginBase`, `FrontendSettingsBase`.
**New module:** `frontend_base/terminal_response.py` (sole owner of all eight builders/streamers + shared helpers).

### Resolve return contract

Core (`frontend_base/plugin_base.py`):
- `resolve_context()` (242–297): returns resolved string or `None`; caches by spec name (process lifetime, no TTL — see **O10**); skips `$prompt` specs (deferred per-request). **Behavior change for the inference path:** a `None`/empty result for a set `raw_expression` is treated as a failure by the inference handler (fail-loud), NOT silently proceeded. The swallow at 279–283 remains for non-inference/other callers but is overridden at the inference call site.
- `_fetch_sync()` (310–336): synchronous wrapper around `_fetch()` in a daemon thread with timeout; #244 fail-loud preserved.
- `_fetch()` (412–417): GET `/ensemble`; `raise_for_status()`; returns plain text.

**Changed responsibility:** the per-provider resolve helpers **return the resolved string (or raise / signal error)** instead of returning `None` and embedding via a side-effect. They **no longer call `embed_context()`**; the inference handler injects the text into the response envelope.

### `frontend_base/terminal_response.py`

Centralizes the structured error-text formatter (single source — resolves the error-format-consistency major), the usage-zeroing supersets, and all eight builders/streamers.

```python
# frontend_base/terminal_response.py
from typing import AsyncIterator
import json, traceback

def extract_error_text(exc: Exception, spec_name: str, expression: str) -> str:
    """SINGLE structured error text shared across ALL providers (no provider envelope).
    Handles both httpx HTTPStatusError (502 path) and raw Url4Interpreter exceptions."""
    tb_str = "".join(traceback.format_exception(exc))
    return (
        f"[url4 error] {spec_name}\n\n"
        f"Expression: {expression[:200]}\n\n"
        f"Error: {exc.__class__.__name__}: {exc}\n\n"
        f"Traceback:\n{tb_str}"
    )

def zeroed_usage(provider: str) -> dict:
    """Superset-of-zeros per provider (see §Usage field shapes)."""
    ...

# builders/streamers (signatures pinned in Locked Decisions) ...
```

**All four frontends call `extract_error_text()`** for the error body; per-frontend error formatting is removed (resolves the "pinned shared function AND per-frontend formatting" contradiction — pick the shared function).

**Resolved-text injection target per provider:** Anthropic → `content[0].text`; OpenAI → `output[0].content[0].text`; Gemini → `candidates[0].content.parts[0].text`; Ollama → `message.content`.

### Settings changes — `embed_target`, `embed_mode`, `system_prompt`

**O2 is escalated, not pinned here** (see Open Questions). To keep the rewrite implementable regardless of the O2 outcome, the **interim, non-breaking behavior** is fixed: the inference paths **stop reading** `embed_target`/`embed_mode`/`system_prompt` (the `_embed_context` calls are deleted), but the fields **remain defined** in `FrontendSettingsBase` (and the ollama `embed_target` override is removed since it is now meaningless). Whether to then HARD-REMOVE the fields (breaking configs that set them) or SOFT-DEPRECATE (keep defined, log a warning when present, ignore) is **O2**. This avoids the internal contradiction (deleting fields the rewrite cannot proceed without deciding) by separating "stop using" (locked) from "remove the field" (O2).

**Retained regardless:** `upstream_url` (non-inference passthrough), `active_spec`, `backend_url`, `resolve_timeout`, `session_service_url`, remainder of `FrontendSettingsBase`.

### Summary of shared changes

| Component | Change | Effect |
|-----------|--------|--------|
| `FrontendSettingsBase` | Stop READING `embed_target`/`embed_mode`/`system_prompt` on inference; field removal gated on O2 | Interim: defined-but-unused |
| `FrontendPluginBase.resolve_context()` | Signature unchanged; inference call site treats None/empty (set spec) as failure | 242–297 + handler override |
| `resolve_prompt_expression()` / `resolve_static_context()` (all) | Return resolved string (or error dict); no embed | Body refactored |
| Per-provider `_embed_context()` / `_inject_system_*()` | Delete | No longer called |
| Per-provider `_extract_last_user_text()` | Keep (input fork) | Usage restricted |
| Inference handlers | Resolve → build/stream helpers; branch error on `is_streaming` | Per provider |
| Non-inference routes | Continue upstream forwarding; bypass url4 entirely | Unchanged |
| `frontend_base/terminal_response.py` | New module: sole owner of builders/streamers + `extract_error_text` | Shared |

---

## Non-inference endpoints (consolidated decision)

All of these **KEEP their upstream forward** (use `upstream_url`); none touch the ensemble. **Passthrough routes MUST bypass url4 entirely and forward the request body UNMODIFIED to upstream — unchanged by the rewrite.**

| Frontend | Route(s) | Methods | Decision | Anchor |
|----------|----------|---------|----------|--------|
| claude | `/v1/{path:path}` catchall (e.g. `GET /v1/models`, OAuth, **`POST /v1/messages/count_tokens`**) | GET, POST | KEEP upstream forward (UNCHANGED) | proxy.py:287–289 |
| claude | `/api/{path:path}` (telemetry, org mgmt) | GET, POST, PUT, PATCH, DELETE | KEEP upstream forward (UNCHANGED) | proxy.py:347–378 |
| codex | `/v1/{path:path}` catchall (`/v1/models`, `/v1/assistants`, `/v1/threads/...`) | GET, POST | KEEP upstream forward (UNCHANGED) | proxy.py:420–450 |
| gemini | `:countTokens`, `:embedContent`, `:batchEmbedContents`, other non-generate `:` verbs (POST) | POST | KEEP upstream forward (handled INSIDE `proxy_gemini` via verb allow-list) | proxy.py:140–164 |
| gemini | `GET /v1beta/models/{model_path}` (model metadata / list) | GET | KEEP upstream forward (UNCHANGED) | proxy.py:159–162 |
| gemini | `/v1beta/{path:path}` catchall (`/v1beta/cachedContent`, etc.) | GET, POST | KEEP upstream forward (UNCHANGED) | proxy.py:318–342 |
| ollama | `/api/{path:path}` (`/api/tags`, `/api/show`, `/api/pull`, `/api/embeddings`) | GET, POST | KEEP upstream forward (UNCHANGED) | proxy.py:446–453 |

Notes:
- **Inference routes only:** claude `POST /v1/messages`; codex `POST /v1/responses`; gemini `POST .../{model}:generateContent` and `:streamGenerateContent`; ollama `POST /api/chat`.
- **claude `POST /v1/messages/count_tokens`** is a passthrough: it does NOT match the exact `/v1/messages` route, falls to the `/v1/{path}` catchall, and MUST continue forwarding upstream. Add a regression test asserting it is NOT terminated. The synthesized `/v1/messages` handler must not swallow it.
- **gemini `:countTokens`/`:embedContent`** hit `proxy_gemini` (the `:path` capture), NOT the `/v1beta/{path}` catchall — so the verb allow-list inside `proxy_gemini` is what keeps them as passthrough. Regression test required.
- `upstream_url` and `_build_headers()` are retained **solely** for these passthrough routes.

---

## Error & Degraded Contract (PR #244 "blocking and screaming")

1. **Block** on resolution. Default `resolve_timeout = 1200s`.
2. **Triggers (uniform, locus-agnostic):** timeout; `/ensemble` 502 (httpx `HTTPStatusError`); in-process `Url4Interpreter` exception; `on_error=collect` insufficient partials; **static spec resolving to None/empty** (fail-loud override).
3. **Loud, fake-200:** capture the exception (or synthesize one for the None-static case), format via `terminal_response.extract_error_text()` (url4 header, expression, error class+message, full traceback), build a provider-shaped **HTTP 200** envelope with the error text in the message body. **Never raise HTTPException; never return HTTP 5xx to the CLI.**
4. **Branch on `is_streaming` for every provider, routing the error text through the SAME success frame generator:** claude `stream_anthropic_sse`; codex `stream_openai_sse(..., status="failed")`; gemini `stream_gemini_chunks` (SSE-or-JSON-array); ollama `stream_ollama_ndjson`. This guarantees a terminating frame and fixes the pre-existing streaming-request-gets-unary-error bug.
5. **Negative cache + bounded/loop-aware fetch (#244) preserved:** `resolve_context()` cache (242–297) and `_fetch_sync()` thread+timeout (310–336) survive intact and feed the builders.

Per-provider error status: claude fake-200 `stop_reason=end_turn`; codex HTTP 200 `status:"failed"`; gemini HTTP 200 `finishReason:"STOP"`; ollama HTTP 200 `done:true, done_reason:"stop"`.

---

## Unchanged: AIGateway & concurrency (#245)

- The inference route no longer calls the upstream provider directly, so the **direct proxy leg is removed**.
- The ensemble's **internal sub-calls** to `/claude`, `/codex`, `/gemini`, `/ollama` still go through AIGateway and respect per-provider concurrency caps (e.g., `AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES={"anthropic":1}` per #245). UNCHANGED.
- `/ensemble` (`url4_executor/routes.py:84–164`) continues to return a `PlainTextResponse` with the resolved string; non-ensemble shapes fall through to the base `Url4Interpreter` (routes.py:117–122). Its dispatch to internal backend sub-routes is unchanged.
- **Grounding note:** verify the `/claude`,`/codex`,`/gemini` internal sub-routes' AIGateway dispatch when wiring tests; the cap behavior is asserted from #245 and must be confirmed against the sub-route definitions during M6.
- **Frontend-side request concurrency** under the new blocking model is NOT capped by this spec — see **O14**.

---

## Test Strategy

### Unit — builders & streamers

- `build_anthropic_message`: role/content/usage-superset-zeros; `stop_reason=end_turn`.
- `stream_anthropic_sse`: parse with a real SSE line-buffer (split on `\n\n`); assert sequence `message_start → ping → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`; full text present; no `[DONE]`.
- `build_openai_response`: `created_at` present (int); `output[0]` has `id`/`status`/`content`; usage superset.
- `stream_openai_sse`: split on `\n\n`, assert EACH event JSON-decodes independently; full canonical 9-event order; `status:"in_progress"` (not `processing`); stable `item_id` across events; `created_at`; `sequence_number` monotonic; no `[DONE]`.
- `build_gemini_response`: schema, `finishReason=STOP`, camelCase `usageMetadata` zeros, `modelVersion` present.
- `stream_gemini_chunks`: default emits a **JSON array** `[{...}]` parseable by `json.loads(whole_body)` with `application/json`; `alt_sse=True` emits `data: {...}\n\n` with `text/event-stream`.
- `build_ollama_response` / `stream_ollama_ndjson`: `Content-Type: application/x-ndjson`; two NDJSON lines; EVERY line (incl. terminal) JSON-decodes and carries a `message` field; last line `done:true, done_reason:"stop"`; model echoed.
- Newline preservation: result with embedded `\n` survives in the delta.

### Integration — no upstream calls on inference

Mock the resolution locus (`frontend_base.plugin_base._fetch_sync` for the HTTP path, or `Url4Interpreter.evaluate` for in-process), not the real provider. Assert a synthesized provider envelope containing the mocked text and NO httpx call to `api.anthropic.com` / `api.openai.com` / `generativelanguage.googleapis.com` / `localhost:11434`.

```python
async def test_proxy_returns_ensemble_result():
    with mock.patch("frontend_base.plugin_base._fetch_sync") as mock_fetch:
        mock_fetch.return_value = "Ensemble result text"
        resp = client.post("http://localhost:9100/v1/messages", json={...})
        mock_fetch.assert_called_once()
        assert "Ensemble result text" in resp.json()["content"][0]["text"]
```

### Per-frontend E2E

- codex streaming → synthetic OpenAI SSE; each event decodes independently; `status:"in_progress"`/`completed`; no `[DONE]`; no `api.openai.com`.
- ollama streaming → `application/x-ndjson`; parse NDJSON; last line `done:true, done_reason:"stop"`; no upstream.
- gemini: unary static spec; streaming `$prompt`; streaming `?alt=sse` (SSE) vs default (JSON array); **`:countTokens` forwards upstream (not synthesized)**; GET passthrough; `/v1beta/{path}` catchall.
- claude: **`POST /v1/messages/count_tokens` forwards upstream** (regression).

### Error-path tests

- `test_<provider>_ensemble_timeout_returns_fake_200`: resolution raises `TimeoutError`; HTTP 200; `[url4 error]` + `timed out` in content.
- `test_<provider>_streaming_error_terminates`: error + `stream=true`; assert error text in the stream AND a terminating frame (`message_stop` / `response.completed` / array-close / `done:true`).
- `test_static_spec_none_is_fail_loud`: static spec resolves to None/empty → error envelope (NOT blank 200).
- `test_in_process_interpreter_exception`: in-process locus raises → same error envelope shape as the 502 path.

### Existing-test migration

Tests asserting upstream httpx calls are rewritten to mock the resolution locus and assert no upstream call. Per-frontend:
- claude `test_proxy.py`: replace `test_proxy_non_streaming`, `test_proxy_forwards_headers`; add SSE/error-streaming tests; rewrite `test_e2e_claude_frontend.py` to assert synthesized response; add catchall tests (`/v1/models`, `/api/*`, `count_tokens`).
- codex: add unary, streaming (independent-event-decode), streaming-error, non-streaming-error, catchall, `$prompt`, static.
- gemini `tests/test_proxy.py`: keep `TestExtractLastUserText`/`TestReplaceUserText`; delete `TestInjectSystemContext`/`TestEmbedContext`; add unary-static, streaming-`$prompt`, `?alt=sse` vs JSON-array default, timeout-fake-200, GET passthrough, `:countTokens` passthrough, catchall; new `tests/test_response_builders.py`. **No gemini session-persistence tests** (gemini stays save-less).
- ollama `tests/test_proxy.py`: delete `test_inject_*`; update `test_non_streaming_passthrough_no_spec`, `test_streaming_ndjson_relay`, `test_prompt_spec_substitution`; keep `test_authorization_forwarded_other_stripped`, `test_catchall_passthrough_tags`; add empty-resolved-text, synthetic-NDJSON (complete frames), timeout (streaming + unary), model-echo, usage-zero. Swap upstream-mock fixtures for a mocked `plugin.resolve_context()` / `MockPlugin`.

---

## Docs to update

- **README / architecture:** rename "Transparent Proxy" → "Ensemble-Terminal Frontend Proxy"; state inference routes no longer forward upstream; the ensemble (or in-process interpreter) is the only upstream-facing path, via its sub-routes/AIGateway.
- **Plugin READMEs** (all four): remove "forwards to <upstream>"; add "terminal response synthesis"; ollama doc clarifies NDJSON (NOT SSE); gemini doc enumerates inference-vs-passthrough verbs.
- **Settings/config docs:** mark `embed_target`/`embed_mode`/`system_prompt` no longer read on inference (deprecation pending O2).
- **Error-handling docs:** document the fake-200 contract (timeout/502/in-process/static-None → HTTP 200 with error text), the `resolve_timeout` blocking window, the two resolution loci, and link to PR #244.
- **CLAUDE.md:** add an "Inference Routes" section (before/after, concurrency model, two loci, #244 error contract, static-spec fail-loud behavior change).
- **CHANGELOG.md:** new entry, including the static-spec fail-loud behavior change.

---

## Milestone Outline

- **M1 — Shared terminal-response infrastructure (1–2 days):** create `frontend_base/terminal_response.py` (`extract_error_text`, `zeroed_usage`, the eight builders/streamers with pinned signatures and wire formats); add the inference-call-site fail-loud override for None/empty static results; unit tests for error paths (timeout, 502, in-process exception, partial results) and independent-event-decode for codex SSE. **All eight builder/streamer functions live exclusively here; per-frontend modules import/re-export only.**
- **M2 — claude_frontend (1 day):** wire `build_anthropic_message` / `stream_anthropic_sse` (with `ping`, superset usage); refactor `proxy_messages()` and the resolve-helper tuple contract; delete `_forward_*`/`_embed_context`/`_inject_system_context`; keep `/v1/{path}` (+ `count_tokens` passthrough) + `/api/{path}`; unit + E2E (no `api.anthropic.com`).
- **M3 — codex_frontend (1 day):** wire `build_openai_response` / `stream_openai_sse` (full canonical sequence, `created_at`, `in_progress`, stable item_id, `\n\n` framing); error envelope `status:"failed"`; unit + E2E.
- **M4 — gemini_frontend (1 day):** wire `build_gemini_response` / `stream_gemini_chunks` (JSON-array default, SSE on `?alt=sse`); implement the verb allow-list inside `proxy_gemini` (`:countTokens`/`:embedContent` passthrough); gemini stays save-less; keep GET + `/v1beta/{path}` passthroughs; unit + E2E (incl. `:countTokens` passthrough).
- **M5 — ollama_frontend (1 day):** wire `build_ollama_response` / `stream_ollama_ndjson` (complete frames, NDJSON not SSE); delete `_embed_context` + `_inject_system_message`; remove `embed_target` override; keep `/api/{path}` passthrough; unit + E2E.
- **M6 — Testing, docs, integration (1–2 days):** migrate all proxy tests to mock the resolution locus; negative tests (no real-upstream calls on inference); verify non-inference routes still forward (incl. claude `count_tokens`, gemini `:countTokens`); confirm AIGateway sub-route dispatch (#245 grounding); cross-frontend integration (same spec → all four return the same result in their native format); docs/CLAUDE.md/changelog incl. static-spec fail-loud.

### Success criteria

1. All four frontends resolve inference via the ensemble (HTTP or in-process). 2. No HTTP calls to `api.anthropic.com` / `api.openai.com` / `generativelanguage.googleapis.com` / `localhost:11434` from inference routes. 3. HTTP 200 provider-native fake responses. 4. Streaming synthesized with a single delta carrying the full result, in the exact wire format (claude SSE `\n\n`+ping; codex SSE `\n\n`+full event sequence; gemini SSE-or-JSON-array; ollama NDJSON). 5. timeout/502/in-process/static-None → HTTP 200 with visible error text (never 5xx); streaming errors terminate. 6. Coverage: builders, streamers (independent-frame-decode), error paths, no-upstream integration, verb-passthrough regressions. 7. Docs + behavior-change notes updated. 8. Non-inference routes still forward upstream (incl. `count_tokens`, `:countTokens`, `:embedContent`). 9. AIGateway caps apply only to ensemble sub-calls. 10. All E2E tests pass with the resolution locus mocked.

---

## Open Questions / Risks

- **O1 — RESOLVED.** Usage shapes pinned as supersets-of-zeros per provider (claude includes `cache_*`; codex full set; gemini camelCase `usageMetadata`; ollama duration/eval). Anthropic `Usage` is `extra="allow"` (models.py:134), so extra zero fields are safe. Confirm each CLI tolerates the superset during M6 smoke tests.
- **O2 — Dead-settings removal vs graceful deprecation (ESCALATED, human decision).** The inference paths stop READING `embed_target`/`embed_mode`/`system_prompt` (locked). Whether to then HARD-REMOVE the fields from `FrontendSettingsBase` (breaks configs that set them; per-session override attempts fail validation) or SOFT-DEPRECATE (keep defined, log a warning, ignore) is undecided. Pick one before final field removal; the rewrite proceeds either way under the interim "defined-but-unused" state.
- **O3 — RESOLVED.** Single shared `terminal_response.py` owns all eight builders/streamers; per-frontend modules import/re-export only.
- **O4 — RESOLVED.** Gemini default (non-`?alt=sse`) streaming emits a true JSON ARRAY `[{...}]` with `application/json` (matching real `streamGenerateContent`); `?alt=sse` emits `data: {...}\n\n`. Verify against the actual Gemini CLI in M4/M6.
- **O5 — RESOLVED.** The claude `$prompt` path uses the tuple-returning resolve helper (`(resolved_text, error_dict)`); no `resolved_text = last_user_text` placeholder.
- **O5b — Empty `$prompt` result semantics (ESCALATED, human decision).** Distinct from static-None (which is fail-loud). If a `$prompt` spec legitimately resolves to `""`, is that an empty-but-valid assistant turn or an error? Decide uniformly across providers and add empty-result E2E tests for ALL four (not just ollama). Note Codex CLI may treat an empty `output` as incomplete — verify.
- **O6 — Static-spec + CLI-prompt / multi-turn semantics (ESCALATED, human decision).** For predetermined (no `$prompt`) specs the CLI prompt is ignored and identical content (with fresh random id + zero usage) is returned every turn. Decide: (a) declare static-spec frontends single-turn/stateless and document that follow-ups are ignored, or (b) require the static path to incorporate the latest user turn. Interacts with **O11**.
- **O7 — Session save on streaming (PARTIALLY RESOLVED).** Locked: streaming `session.save` receives the SAME dict produced by `build_<provider>_*()` directly (NOT re-parsed synthesized frames); fired exactly once. Open: whether error-envelope turns are persisted at all — escalated.
- **O7b — Gemini session save (ESCALATED, scoped-out by default).** Gemini currently has NO `save_response` (only `enrich_request`). This spec keeps it save-less. Adding save is net-new behavior (build the save dict from the synthesized response) and is out of scope unless explicitly requested.
- **O8 — Feature-flagged rollout (optional, human decision).** `SF_ENSEMBLE_TERMINAL_<FRONTEND>=true` per frontend with old code retained for rollback, vs direct cutover at M6.
- **O9 — Multi-turn history into the ensemble (ESCALATED, human decision).** All four extractors take only the LAST user message. With no upstream, prior turns are lost — the ensemble sees only the latest turn. Decide: pass the full transcript as the blob, or document frontends as single-shot with intentionally-dropped history. Without a decision, multi-turn behavior silently regresses.
- **O10 — Resolve cache lifecycle (ESCALATED, human decision).** `resolve_context()` caches per spec name for the process lifetime with no TTL/invalidation. Document behavior across live `active_spec` changes (a stale prior spec could be re-served if switched back); consider periodic re-resolution for static specs.
- **O11 — Deterministic-vs-random id + non-zero usage for CLI budget logic (ESCALATED, human decision).** Fresh random ids and zero usage every turn may confuse CLI context-window accounting (always 0 tokens) and conversation-state keying. Decide id policy (random vs deterministic) and whether usage should report a plausible non-zero count. Interacts with O6.
- **O12 — Gemini `responseId` (ESCALATED, low risk).** `modelVersion` is included; whether to also emit a synthetic `responseId` depends on CLI tolerance — verify in M4.
- **O13 — Ollama model-existence divergence (ESCALATED, human decision).** Synthesized `/api/chat` answers for a model the upstream Ollama may not host, while passthrough `/api/show`/`/api/tags` reflect the real upstream. Decide whether to synthesize `/api/show`/`/api/tags` for the active model or require the upstream to host it.
- **O14 — Frontend-side request concurrency / disconnect (ESCALATED, human decision).** Each `$prompt` turn now BLOCKS the request for up to `resolve_timeout` (1200s) on a full ensemble fan-out; N concurrent CLI turns = N concurrent fan-outs. The fake-stream computes the whole result BEFORE the first frame, so client disconnect/cancellation does not propagate to the in-flight ensemble, and the `_fetch_sync` daemon thread (plugin_base.py:326) cannot be cancelled today. Decide: a per-frontend in-flight concurrency limit/queue, and disconnect handling (`request.is_disconnected()` / `asyncio.CancelledError`) — call out the daemon-thread non-cancellability limitation.
- **O15 — Startup auth / model-list dependency (ESCALATED, human decision).** Non-inference OAuth/model-list/`/api/show` routes still forward to the REAL upstream, so a CLI's startup auth/validation may still require valid real-provider credentials and may reject a fictitious ensemble model alias (the echoed `model`). Determine, per CLI, which startup calls must reach a real upstream, whether real provider keys remain mandatory, and whether model-list must be synthesized to include the active alias. If the goal is to run without real provider keys, the passthrough auth/model-list routes must also be stubbed — currently out of scope.
- **O16 — Active spec terminating in a model call (ESCALATED, low priority).** The ensemble supports non-model expressions (raw fetch, collection reduce); `/ensemble` falls through to the base interpreter for non-ensemble shapes. Confirm whether the active spec is REQUIRED to end in a model/reducer call or may resolve to arbitrary url4 output, and whether wrapping non-model text as an assistant message with zeroed usage / `finishReason=STOP` is intended.

---

## Review Changelog

**cli-compat lens**
- Codex SSE single-`\n` framing (blocker) — FIXED inline: every codex SSE frame is `data: {json}\n\n`; test asserts each event decodes independently.
- Gemini default non-SSE format pinned wrong (blocker) — FIXED inline (O4 resolved): default emits a true JSON ARRAY `[{...}]` with `application/json`; `?alt=sse` emits `data: {...}\n\n`.
- Codex missing canonical events / malformed created+completed (blocker) — FIXED inline: full 9-event sequence (`response.created`, `in_progress`, `output_item.added`, `content_part.added`, `output_text.delta`, `output_text.done`, `content_part.done`, `output_item.done`, `completed`) with `created_at`, `output:[]`, item `id`/`status`/`content`, `sequence_number`/`output_index`/`content_index`.
- Anthropic missing `ping` / "EXACT" overclaim (blocker) — FIXED inline: `ping` frame added after `message_start`; frame language softened to `message_start, ping*, content_block_start, content_block_delta+, content_block_stop, message_delta, message_stop`.
- Codex `created_at` missing in unary+stream (major) — FIXED inline: `created_at: int(time.time())` added everywhere.
- Gemini SSE/array media_type coupling (major) — FIXED inline: array default → `application/json`; SSE → `text/event-stream`.
- Ollama abbreviated error frames (major) — FIXED inline: every NDJSON frame (incl. terminal `done`) carries a complete `message` field; error path reuses the full builder/streamer.
- Codex `status:"processing"` invalid (major) — FIXED inline: `in_progress`/`completed`.
- Gemini Content-Type vs body contradiction (major) — FIXED inline (JSON array + `application/json`).
- Anthropic usage cache fields (minor) — RESOLVED inline: superset-of-zeros pinned (O1).
- Gemini `modelVersion`/`responseId` (minor) — `modelVersion` ADDED inline; `responseId` escalated to O12.
- Codex item-id inconsistency (minor) — FIXED inline: one stable `item_id` across all events; prose and code agree.
- Anthropic streaming-error helper unspecified (question) — FIXED inline: streaming error routes the error text through the SAME `stream_anthropic_sse` generator (terminating `message_stop` guaranteed); same pattern for all four.
- Empty ensemble result handling (question) — ESCALATED to O5b (uniform decision + E2E for all four).

**completeness lens**
- Gemini `:countTokens`/`:embedContent` mis-routed to synthesis (blocker) — FIXED inline: explicit inference verb allow-list inside `proxy_gemini`; all other `:` verbs + GET forward upstream; regression test required.
- Claude `count_tokens` passthrough not locked (blocker) — FIXED inline: listed as a passthrough route; route-precedence confirmed (catchall, not exact `/v1/messages`); regression test required.
- Static-spec identical-content/zero-usage multi-turn break (blocker) — ESCALATED to O6 (+ O11 for id/usage policy); single-turn-vs-incorporate-prompt decision surfaced.
- Session save coupled to upstream stream / re-parse (major) — FIXED inline (O7): save receives the builder dict directly, not re-parsed frames.
- Gemini has no `save_response` today (major) — FIXED inline: gemini stays save-less (O7b); session-persistence tests removed from the gemini matrix.
- Static-spec resolution swallow vs fail-loud (major) — FIXED inline: inference handler treats None/empty static result as a failure (fail-loud override); documented as a deliberate behavior change.
- In-process interpreter bypasses `/ensemble` 502 (major) — FIXED inline: §"Two resolution loci"; error contract is locus-agnostic ("any exception during resolution"); `extract_error_text` handles both.
- Multi-turn history dropped (major) — ESCALATED to O9.
- Client disconnect / cancellation (major) — ESCALATED to O14 (incl. daemon-thread non-cancellability).
- OAuth/auth handshake still needs real upstream (major) — ESCALATED to O15.
- Model-list dependency on real upstream (major) — ESCALATED to O15.
- Ollama `/api/show` vs synthesized `/api/chat` divergence (major) — DOCUMENTED inline + ESCALATED to O13.
- Gemini default-stream array (major, dup of cli-compat) — FIXED inline (JSON array).
- Claude unary-error-on-streaming-request bug (minor) — FIXED inline: handler branches on `is_streaming`; `_build_error_response` refactored to return the dict.
- Empty/None resolved text (minor) — ESCALATED to O5b.
- Resolve cache no invalidation (minor) — ESCALATED to O10.
- Spec must terminate in a model call? (question) — ESCALATED to O16.
- Frontend request concurrency under blocking resolve (question) — ESCALATED to O14.

**grounding & internal consistency lens**
- Resolve-helper contract ambiguity (blocker) — FIXED inline: pinned tuple `(resolved_text, error_dict)`; no body mutation; `_build_error_response` returns a dict.
- Settings-deletion vs O2 contradiction (blocker) — FIXED inline: separated "stop reading on inference" (locked) from "remove the field" (O2); interim defined-but-unused state keeps the rewrite implementable.
- Builder placement unpinned (blocker) — FIXED inline (O3 resolved): single shared `terminal_response.py`; per-frontend re-export only.
- Anthropic usage shape unvalidated (major) — FIXED inline: superset-of-zeros; grounded on `Usage` `extra="allow"` (models.py:134); CLI tolerance confirmed in M6.
- Codex error envelope incomplete (major) — FIXED inline: full `status:"failed"` schema with `created_at`/`output`/`usage`, error text in `output[0].content[0].text`.
- Ollama "one delta" vs real per-chunk NDJSON (major) — DOCUMENTED inline as an intentional simplification; format confirmed NDJSON (not SSE), complete frames; verify against real Ollama clients in M5/M6.
- Inconsistent error formatting across providers (major) — FIXED inline: single shared `extract_error_text()`; per-frontend formatting removed.
- Passthrough routes not confirmed url4-bypassing (major) — FIXED inline: explicit statement that passthrough routes bypass url4 and forward the body unmodified, unchanged by the rewrite.
- AIGateway sub-call claim ungrounded (major) — ACKNOWLEDGED inline: grounding-note added; sub-route dispatch to be confirmed in M6 (route file referenced).
- session.save contract missing (major) — FIXED inline: pseudocode shows save (builder dict) for unary and streaming in all handlers (O7).
- Gemini streaming format unvalidated (minor) — RESOLVED inline (O4 JSON array); CLI verification in M4/M6.
- $prompt-vs-static UX intent (minor) — ESCALATED to O6.
- Cache lifecycle in terminal context (minor) — ESCALATED to O10.
- Helper signatures lacking (minor) — FIXED inline: formal signatures pinned in Locked Decisions.
- Milestone placement ambiguity (minor) — FIXED inline: M1 states all eight functions live exclusively in `terminal_response.py`; per-frontend re-export only.

**Rejected findings:** none. No finding recommended excluding `ollama_frontend` or any other frontend; all four remain first-class terminal endpoints. Ollama's streaming wire format is kept as NDJSON (`application/x-ndjson`, one complete JSON object per line) and is explicitly NOT conflated with SSE throughout.
