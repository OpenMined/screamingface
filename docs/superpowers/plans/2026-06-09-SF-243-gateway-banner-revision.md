# SF-243 (revision): url4 ensemble gateway banner — move from shell-rc wrapper to claude_frontend response

**Status:** proposed — supersedes `docs/superpowers/plans/2026-06-08-SF-243-gateway-banner.md` (the `claude_env_intercept` rc-wrapper approach shipped in PR #257).
**Date:** 2026-06-09

## Context

SF-243 adds a banner that tells the user, when they run `claude` through the ScreamingFace gateway, that their queries are answered by the url4 ensemble gateway and **which active url4 spec** is answering — or warns if none is set.

PR #257 implemented this as a `claude()` shell function injected into the user's `.zshrc`/`.bashrc` by the **`claude_env_intercept`** plugin, printing the banner to stderr at launch.

The problem: that banner is **structurally coupled to one intercept strategy.** There are three mutually-exclusive ways to redirect the `claude` CLI (`docs/architecture/plugin-dependencies.md:184`): `claude-intercept` (hosts-file + sudo), `claude-env-intercept` (shell-rc `ANTHROPIC_BASE_URL`), `mitmproxy-intercept`. Only the shell-rc one can wrap the CLI and print at launch — and **none of the three is enabled in the shipped `apps/server/sf.json`**, while `claude-frontend` IS. So the PR #257 banner is dormant in practice and, even when active, only fires for one of three strategies.

**Decision (this revision):** surface the banner from `claude_frontend` — the always-enabled plugin that produces every `/v1/messages` response — so it appears regardless of intercept strategy. The tradeoff, explicitly accepted: it is **not a launch-time banner**; it renders at the top of the answer to the **first prompt**. The banner must never leak into the ensemble input.

This was validated against the live request path (see "Why this is safe" below): the ensemble input is built at exactly one chokepoint, and both the client message-echo and server-side session enrichment converge there before it runs.

## Approach

Two hook points in `claude_frontend`, plus a render helper, plus tests.

### 1. Render the banner (reuse / relocate the helper)

PR #257 added `render_gateway_banner(spec_name, expression)` in `claude_env_intercept/shellenv.py`. Move/duplicate the **pure text renderer** into `frontend_base` (e.g. `frontend_base/terminal_response.py` or a small `frontend_base/_banner.py`) so it has no dependency on the rc-wrapper plugin. Signature unchanged:

```python
def render_gateway_banner(spec_name: str | None, expression: str | None) -> str: ...
```

Wrap the rendered text in a tight, content-improbable sentinel so it can be stripped later, e.g.:

```
⟦SFGW⟧
  == ScreamingFace url4 ensemble gateway ==
  Your claude queries are answered by this gateway, not api.anthropic.com.
  Active url4 spec: <name>
    <expression>
⟦/SFGW⟧
```

### 2. Inject on the first turn only — into the user-facing response, not the saved copy

In `claude_frontend/proxy.py`, `proxy_messages` (the `/v1/messages` handler, proxy.py:125), **Stage 4**:

- Detect first turn: no assistant role present in `_extract_turns(body)` (proxy.py:71). Helper `_is_first_turn(body) -> bool`.
- Build the banner from the data `claude_frontend` already owns: `plugin.active_spec` + `plugin.get_active_expression()` (`frontend_base/plugin_base.py:235`). On the no-spec path the banner shows the existing warning copy.
- Keep the **saved** response clean; only the **returned/streamed bytes** carry the banner:

```python
result_text = resolved_text or ""
# clean copy is what gets persisted to session state:
response_dict = build_anthropic_message(result_text, model, prompt_text=prompt_blob)
await session.save(response_dict, streaming=is_streaming, tracer=_tracer)

# user-facing copy (first turn only) — banner prepended:
user_text = f"{banner}\n\n{result_text}" if _is_first_turn(body) else result_text
```

- **Unary:** return `build_anthropic_message(user_text, model, response_id=<id of clean dict>, prompt_text=prompt_blob)`. Pass the **same `response_id`** the clean dict produced so dedup/caching keys stay stable (ids are derived from `model + prompt_text + result_text` via `deterministic_id`, terminal_response.py:77 — banner would otherwise perturb them).
- **Streaming:** in the `gen()` loop, emit the banner as the first text delta, then stream `result_text` normally via `stream_anthropic_sse(result_text, model, response_id=..., prompt_text=prompt_blob)`. (Reuse the existing SSE framing; do not invent new event types.)

Banner injection happens **after** `prompt_blob` is built and **after** `session.save`, so neither the ensemble input nor the session store ever sees it.

### 3. Strip the sentinel block when building the ensemble input (the safety net)

The only path you cannot control is the client echoing turn-1's assistant message (with banner) back in history on turn 2+. Strip it at the single chokepoint:

- In `_extract_turns` (proxy.py:71) — or in `serialize_transcript` (terminal_response.py:56) — remove the `⟦SFGW⟧…⟦/SFGW⟧` block (DOTALL, leading-anchored, tolerant of trailing newlines) from **assistant**-role content before it becomes a turn tuple.
- This single point covers **both** sources (proven below): client echo and server-side enrich.

### 4. Retire the rc-wrapper banner from PR #257

- Remove the `build_claude_banner_function` / `claude()`-injection and the `extra_lines` plumbing added to `claude_env_intercept/shellenv.py` + `plugin.py` in PR #257. Keep `add_exports` back-compatible (revert it to the pre-#257 single-arg form, or leave `extra_lines` unused — prefer revert to avoid dead params).
- Net effect: `claude_env_intercept` goes back to "writes `ANTHROPIC_BASE_URL` only"; the banner is no longer tied to it.

## Why this is safe (traced against current code)

`proxy_messages` runs, in order:

```python
body = await request.json()                 # ① client history (echoes turn-1 assistant on turn 2+)
body = await session.enrich(body, ...)      # ② SessionHook.enrich REPLACES body with hook result (_session.py:94)
prompt_blob = serialize_transcript(_extract_turns(body))   # ③ ensemble input — built ONLY from body["messages"]
```

- `_extract_turns` reads exactly one field: `body["messages"]`.
- `enrich` merges any server-side prior turns into that same `body["messages"]` (it returns the possibly-replaced body; proxy reassigns it).
- Therefore a content-strip inside `_extract_turns`/`serialize_transcript` is the **single complete chokepoint** — both the client echo and the enrich-injected turns pass through it. `prompt_blob` is the sole value handed to `$prompt`; there is no second route to the ensemble.
- On **turn 1** the ensemble input is clean by construction (the incoming body has no assistant turn yet; the banner is created afterward). Stripping only ever has to defend turn 2+.

## Critical files

| File | Change |
|---|---|
| `apps/server/src/screamingface/plugins/claude_frontend/proxy.py` | First-turn detect + banner inject (Stage 4, unary + streaming); sentinel-strip in `_extract_turns` |
| `apps/server/src/screamingface/plugins/frontend_base/terminal_response.py` | Relocate `render_gateway_banner` here (or new `_banner.py`); optionally do the strip in `serialize_transcript` |
| `apps/server/src/screamingface/plugins/frontend_base/plugin_base.py` | No change expected — reuse `active_spec` + `get_active_expression()` (:235) |
| `apps/server/src/screamingface/plugins/claude_env_intercept/shellenv.py` | Remove `build_claude_banner_function`; revert `add_exports` to single-arg |
| `apps/server/src/screamingface/plugins/claude_env_intercept/plugin.py` | Drop banner baking from `setup()` |
| `.../claude_frontend/tests/` + `.../claude_env_intercept/tests/test_claude_env.py` | New frontend tests; remove the rc-wrapper banner tests |

## Verification

End-to-end, against the live proxy:

1. **First-turn injects, ensemble clean (turn 1):** POST `/v1/messages` (single user message) with an active `$prompt` spec. Assert: returned content starts with the banner; the value passed to `$prompt`/`/ensemble` (assert on `prompt_blob` / trace attr `url4.result_length` path) contains **no** banner text.
2. **No leak on turn 2:** POST a 2nd request whose `messages` include the turn-1 assistant message verbatim (banner + sentinels), as the claude CLI would replay it. Assert `serialize_transcript(_extract_turns(body))` is banner-free, and the banner is **not** re-injected (only first turn).
3. **Enrich path:** with session enrichment enabled, have the `session.enrich_request` hook inject a prior assistant turn containing the sentinel block; assert it is stripped from `prompt_blob` (covers the server-side path, not just client echo).
4. **Saved copy clean:** assert the `session.save(...)` payload for turn 1 has banner-free assistant content (banner lives only in returned bytes).
5. **No-spec warning:** with no active spec, first-turn response shows the warning banner; empty-envelope behavior otherwise unchanged.
6. **Streaming parity:** repeat (1) with `stream: true`; banner is the first text delta, SSE frame sequence otherwise unchanged; `response_id` matches the unary/clean id.
7. **Regression:** `cd apps/server && uv run pytest` for both plugins; pyright clean; pre-commit green. Run the url4 e2e (`url4_executor/tests/test_e2e_url4.py`) — it lists `claude-env-intercept` in its plugin set, so confirm the rc-wrapper removal doesn't break it.

## Open question to confirm during implementation

Whether `deterministic_id` stability matters downstream (cache/log dedup keyed on msg id). The plan keeps the id derived from the **clean** `result_text` so the banner doesn't change cache keys — confirm no consumer expects the id to match the literally-returned bytes.
