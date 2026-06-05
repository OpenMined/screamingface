# SF-241 — Only Genuine User Prompts Reach /ensemble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Claude Code's auxiliary (utility-model) `/v1/messages` calls — conversation-title generation, topic/"is-new-topic" detection, quota/usage probes — from being resolved through `/ensemble`; answer them with a cheap synthetic envelope so only genuine user turns trigger an ensemble run, **without ever silently dropping a real user turn.**

**Architecture:** `claude_frontend.proxy.proxy_messages` is terminal: when the active url4 spec contains `$prompt` it serializes the full transcript and resolves via `/ensemble`. Today there is **no request classification**, so every `POST /v1/messages` (including Claude Code's Haiku-model background calls) hits `/ensemble`. We insert a classifier at the top of `proxy_messages` (after `model` is parsed, **before** session enrichment / serialization / resolution). A request is **auxiliary** iff: filtering is enabled **AND** it does **not** carry Claude Code's main-loop signature (the `You are Claude Code` identity or a non-empty `tools` array) **AND** its `model` matches the configurable utility-model allowlist (default: contains `haiku`). Auxiliary → return a minimal synthetic Anthropic envelope (empty completion) and return early. Everything else → behave exactly as today.

**Two layers guarantee a real user turn is never stubbed:** (1) the **main-loop override (R0)** forces USER whenever the CC identity/tools are present — this is on *every* real turn but *no* lightweight aux probe, so it protects even a user who runs Haiku as their **main** model; (2) the utility-model allowlist is configurable (set `utility_models: []` or `filter_auxiliary_requests: false` to disable). Both override directions **fail toward `/ensemble`** (the safe direction: a missed aux call costs an extra ensemble run; it never drops a prompt). Every auxiliary decision is logged + recorded on the trace span (fail-loud, never silent).

**Tech Stack:** Python 3.13, FastAPI, pydantic-settings (`FrontendSettingsBase`), pytest (`asyncio_mode = "auto"`), pyright, ruff 0.9.0 (pre-commit pinned).

**Provenance:** Design verified by the `cc-aux-request-classifier-research` workflow (taxonomy of CC Haiku calls + adversarial false-positive review). The adversarial pass rated the model-only design *needs-changes* (silent-drop hole for Haiku-main users) and required the R0 main-loop override folded in below.

**Tickets:** SF-241 (this plan). Siblings SF-242 (desktop Eval Studio UI), SF-243 (CLI launcher banner) are out of scope here.

**Worktree / branch:** `/private/tmp/SF-241-ensemble-user-prompt-filter` on `SF-241-ensemble-user-prompt-filter` (cut from `origin/main` `37685f7`).

**Gate commands (run from `apps/server`):**
- Targeted: `uv run pytest -q -m "not live" src/screamingface/plugins/claude_frontend/`
- Full gate (mirror CI): `uv run pytest -q -m "not live" tests/ src/screamingface/plugins/`
- Types: `uv run pyright`
- Pre-commit: `pre-commit run --files <changed files>` (ruff + ruff-format; re-stage if reformatted)

---

## File Structure

| File | Responsibility |
|---|---|
| `src/screamingface/plugins/claude_frontend/_classifier.py` (Create) | Pure, testable classifier: `is_auxiliary_request(body, *, utility_models, enabled)`, the `is_cc_main_loop` (R0) + `is_utility_model` helpers, and `AUX_STUB_TEXT`. No FastAPI/IO. |
| `src/screamingface/plugins/claude_frontend/plugin.py` (Modify) | Add `filter_auxiliary_requests: bool` and `utility_models: list[str]` to `ClaudeFrontendSettings`. |
| `src/screamingface/plugins/claude_frontend/proxy.py` (Modify) | Gate at top of `proxy_messages`: auxiliary → synthetic envelope (unary + streaming), return early before session/ensemble. |
| `src/screamingface/plugins/claude_frontend/tests/test_classifier.py` (Create) | Unit tests for the classifier, including the R0 main-loop-Haiku safety case. |
| `src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py` (Create) | Proxy tests: aux → synthetic + resolution NOT called; user/main-loop → resolution called. |

---

## Task 1: Settings — utility-model allowlist + master switch

**Files:**
- Modify: `src/screamingface/plugins/claude_frontend/plugin.py`
- Test: `src/screamingface/plugins/claude_frontend/tests/test_classifier.py`

- [ ] **Step 1: Write the failing test**

Create `src/screamingface/plugins/claude_frontend/tests/test_classifier.py`:

```python
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings


def test_settings_defaults_enable_aux_filtering():
    s = ClaudeFrontendSettings()
    assert s.filter_auxiliary_requests is True
    assert s.utility_models == ["haiku"]


def test_settings_utility_models_can_be_cleared():
    # A user who runs Haiku as their MAIN model can disable model-based filtering.
    s = ClaudeFrontendSettings(utility_models=[])
    assert s.utility_models == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_classifier.py::test_settings_defaults_enable_aux_filtering`
Expected: FAIL — `AttributeError`/`ValidationError` (fields don't exist).

- [ ] **Step 3: Add the settings fields**

In `src/screamingface/plugins/claude_frontend/plugin.py`, add to `class ClaudeFrontendSettings(FrontendSettingsBase)` (alongside `upstream_url` / `listen_port` / `default_backend_path`):

```python
    filter_auxiliary_requests: bool = True
    """When True, requests whose ``model`` matches ``utility_models`` AND which do
    NOT carry Claude Code's main-loop signature are answered with a synthetic stub
    instead of being resolved via /ensemble (Claude Code's Haiku title/topic/quota
    calls). Set False for pure today-behavior."""

    utility_models: list[str] = ["haiku"]
    """Case-insensitive substrings identifying the utility/auxiliary model tier.
    A request's ``model`` matches if it contains any of these (so 'haiku' covers
    claude-3-5-haiku and claude-haiku-4-5, dated or undated). Set to ``[]`` to
    disable model-based classification (e.g. when Haiku is the user's MAIN model)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_classifier.py -k settings`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/screamingface/plugins/claude_frontend/plugin.py src/screamingface/plugins/claude_frontend/tests/test_classifier.py
git commit -m "feat(claude-frontend): add utility_models allowlist settings (SF-241)"
```

---

## Task 2: Classifier — main-loop override (R0) + utility allowlist

**Files:**
- Create: `src/screamingface/plugins/claude_frontend/_classifier.py`
- Test: `src/screamingface/plugins/claude_frontend/tests/test_classifier.py`

- [ ] **Step 1: Write the failing test**

Append to `src/screamingface/plugins/claude_frontend/tests/test_classifier.py`:

```python
import pytest

from screamingface.plugins.claude_frontend._classifier import (
    AUX_STUB_TEXT,
    is_auxiliary_request,
    is_cc_main_loop,
    is_utility_model,
)

UTIL = ["haiku"]


# --- is_utility_model: substring, case-insensitive, dated + undated ---
@pytest.mark.parametrize(
    "model",
    ["claude-3-5-haiku-20241022", "claude-haiku-4-5", "claude-haiku-4-5-20251001", "CLAUDE-HAIKU-4-5"],
)
def test_haiku_models_match_utility(model):
    assert is_utility_model(model, UTIL) is True


@pytest.mark.parametrize("model", ["claude-opus-4-1-20250805", "claude-sonnet-4-5", ""])
def test_non_haiku_models_do_not_match_utility(model):
    assert is_utility_model(model, UTIL) is False


def test_empty_utility_list_matches_nothing():
    assert is_utility_model("claude-haiku-4-5", []) is False


# --- R0 main-loop override: identity OR tools => main loop ---
def test_cc_identity_in_system_is_main_loop():
    body = {"system": [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI."}]}
    assert is_cc_main_loop(body) is True


def test_string_system_with_identity_is_main_loop():
    body = {"system": "You are Claude Code, Anthropic's official CLI for Claude."}
    assert is_cc_main_loop(body) is True


def test_nonempty_tools_is_main_loop():
    body = {"system": "Generate a title.", "tools": [{"name": "Bash"}]}
    assert is_cc_main_loop(body) is True


def test_aux_probe_is_not_main_loop():
    body = {"system": "Generate a concise title for this conversation.", "messages": [{"role": "user", "content": "x"}]}
    assert is_cc_main_loop(body) is False


# --- is_auxiliary_request: the composed decision ---
def test_haiku_aux_probe_is_auxiliary():
    body = {"model": "claude-haiku-4-5", "max_tokens": 1, "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is True


def test_haiku_MAIN_LOOP_turn_is_NOT_auxiliary():
    # SAFETY: Haiku-as-main user. Real turn carries identity + tools => USER, never stubbed.
    body = {
        "model": "claude-haiku-4-5-20251001",
        "system": [
            {"type": "text", "text": "x-anthropic-billing-header: cc_entrypoint=cli; cch=fa1;"},
            {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."},
        ],
        "tools": [{"name": "Bash"}],
        "messages": [{"role": "user", "content": "real question"}],
    }
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is False


def test_opus_turn_is_never_auxiliary():
    body = {"model": "claude-opus-4-1-20250805", "messages": [{"role": "user", "content": "hi"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is False


def test_disabled_filtering_is_never_auxiliary():
    body = {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=False) is False


def test_empty_utility_models_is_never_auxiliary():
    body = {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=[], enabled=True) is False


def test_stub_text_is_empty_str():
    assert AUX_STUB_TEXT == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_classifier.py -k "utility or main_loop or auxiliary or stub"`
Expected: FAIL — `ModuleNotFoundError: ..._classifier`.

- [ ] **Step 3: Write the classifier module**

Create `src/screamingface/plugins/claude_frontend/_classifier.py`:

```python
"""User-vs-auxiliary request classification for claude_frontend.

Claude Code issues non-user ``/v1/messages`` calls (conversation-title generation,
topic/"is-new-topic" detection, quota/usage probes) on a utility model (Haiku).
Those must NOT be resolved through /ensemble. A request is auxiliary iff:

    filtering enabled  AND  NOT a Claude Code main-loop turn (R0 override)  AND
    its ``model`` matches the configured utility-model allowlist.

The R0 main-loop override (``is_cc_main_loop``) keys on Claude Code's identity
("You are Claude Code") or a non-empty ``tools`` array — present on EVERY real
user turn but absent on lightweight aux probes. It guarantees a genuine user turn
is never stubbed, even when the user runs Haiku as their MAIN model. Both the
override and the allowlist fail toward /ensemble (the safe direction): a missed
aux call costs one extra ensemble run; a real prompt is never dropped (SF-241).
"""

from __future__ import annotations

from typing import Any

# Minimal synthetic completion for auxiliary requests. Empty == a well-formed,
# zero-token 200. Correct for the header-only probes (quota / verify_api_key
# discard the body); cosmetic-only for title/topic (CC keeps prior/default title).
AUX_STUB_TEXT = ""

_CC_IDENTITY_MARKER = "you are claude code"


def _system_text(body: dict[str, Any]) -> str:
    """Lowercased concatenation of the request's system prompt text blocks."""
    system = body.get("system", "")
    if isinstance(system, str):
        return system.lower()
    if isinstance(system, list):
        parts = [
            block["text"]
            for block in system
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return " ".join(parts).lower()
    return ""


def is_cc_main_loop(body: dict[str, Any]) -> bool:
    """R0 USER-override: True if the request carries Claude Code's main-loop
    signature — the ``You are Claude Code`` identity, or a non-empty ``tools``
    array. Present on every real user turn, absent on aux probes. Errs toward
    main-loop (and thus /ensemble) — the safe direction.
    """
    tools = body.get("tools")
    if isinstance(tools, list) and tools:
        return True
    return _CC_IDENTITY_MARKER in _system_text(body)


def is_utility_model(model: str, utility_models: list[str]) -> bool:
    """True if ``model`` contains any configured utility-model substring
    (case-insensitive). Empty ``model`` or empty ``utility_models`` → False.
    """
    if not model or not utility_models:
        return False
    lowered = model.lower()
    return any(u.lower() in lowered for u in utility_models)


def is_auxiliary_request(
    body: dict[str, Any], *, utility_models: list[str], enabled: bool
) -> bool:
    """True => auxiliary (utility-model probe) => synthetic stub, skip /ensemble.

    Order: master switch → R0 main-loop override (force USER) → utility-model
    allowlist. The R0 override is checked BEFORE the model allowlist so a real
    user turn on a utility model is never misclassified.
    """
    if not enabled:
        return False
    if is_cc_main_loop(body):
        return False
    return is_utility_model(body.get("model", ""), utility_models)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_classifier.py`
Expected: PASS (all classifier + settings tests, incl. `test_haiku_MAIN_LOOP_turn_is_NOT_auxiliary`).

- [ ] **Step 5: Commit**

```bash
git add src/screamingface/plugins/claude_frontend/_classifier.py src/screamingface/plugins/claude_frontend/tests/test_classifier.py
git commit -m "feat(claude-frontend): classifier with CC main-loop override + utility allowlist (SF-241)"
```

---

## Task 3: Gate proxy_messages — auxiliary → synthetic, never /ensemble

**Files:**
- Modify: `src/screamingface/plugins/claude_frontend/proxy.py`
- Test: `src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py`

- [ ] **Step 1: Write the failing test**

Create `src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py`. We patch `proxy.resolve_prompt_expression` (async) so we can assert exactly when resolution runs.

```python
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

import screamingface.plugins.claude_frontend.proxy as proxy_mod
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def _app(*, utility_models: list[str], enabled: bool = True) -> FastAPI:
    settings = ClaudeFrontendSettings(
        active_spec="MainOne",
        utility_models=utility_models,
        filter_auxiliary_requests=enabled,
    )
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "($prompt)!'spec'"
    app = FastAPI()
    app.state.blob_store = None
    app.include_router(create_router(settings, app=app, plugin=plugin, hooks=None))
    return app


def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://test") as client:
        return client.post("/v1/messages", json=body)


@pytest.fixture
def patched_resolve(monkeypatch):
    mock = AsyncMock(return_value=("RESOLVED-BY-ENSEMBLE", None))
    monkeypatch.setattr(proxy_mod, "resolve_prompt_expression", mock)
    return mock


def test_haiku_aux_probe_synthesized_without_resolution(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(app, {"model": "claude-haiku-4-5", "max_tokens": 1,
                       "messages": [{"role": "user", "content": "quota"}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "message" and body["role"] == "assistant"
    assert body["content"][0]["text"] == ""           # empty synthetic stub
    patched_resolve.assert_not_called()                # /ensemble path never entered


def test_haiku_aux_streaming_synthesized_without_resolution(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(app, {"model": "claude-haiku-4-5", "stream": True, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "topic?"}]})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert b"message_start" in resp.content and b"message_stop" in resp.content
    patched_resolve.assert_not_called()


def test_haiku_main_loop_turn_reaches_ensemble(patched_resolve):
    # SAFETY: Haiku-as-main real turn (identity + tools) => USER => /ensemble runs.
    app = _app(utility_models=["haiku"])
    resp = _post(app, {
        "model": "claude-haiku-4-5-20251001", "max_tokens": 1024,
        "system": [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI."}],
        "tools": [{"name": "Bash"}],
        "messages": [{"role": "user", "content": "real question"}],
    })
    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()


def test_opus_turn_reaches_ensemble(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(app, {"model": "claude-opus-4-1-20250805", "max_tokens": 1024,
                       "messages": [{"role": "user", "content": "hi"}]})
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()


def test_disabled_filtering_lets_haiku_reach_ensemble(patched_resolve):
    app = _app(utility_models=["haiku"], enabled=False)
    resp = _post(app, {"model": "claude-haiku-4-5", "max_tokens": 1,
                       "messages": [{"role": "user", "content": "quota"}]})
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py -k aux_probe`
Expected: FAIL — without the gate, the Haiku probe enters resolution; `patched_resolve` IS called and `content[0].text` is `"RESOLVED-BY-ENSEMBLE"`, not `""`.

- [ ] **Step 3: Add the gate to `proxy_messages`**

In `src/screamingface/plugins/claude_frontend/proxy.py`:

(a) Add the import near the other `claude_frontend` imports (around line 31-35):

```python
from screamingface.plugins.claude_frontend._classifier import (
    AUX_STUB_TEXT,
    is_auxiliary_request,
)
```

(b) In `proxy_messages`, immediately after `_record_trace_id(request)` (line 133) and **before** the `# Stage 1: session enrichment` block (line 135), insert:

```python
        # Auxiliary (utility-model) requests — Claude Code's title/topic/quota Haiku
        # calls — must never reach /ensemble. The classifier forces USER for any real
        # main-loop turn (identity/tools present) BEFORE the model check, so a real
        # prompt is never stubbed. Auxiliary → minimal synthetic envelope, returned
        # BEFORE session enrichment and url4 resolution (SF-241). Fail-loud: the
        # decision is logged and recorded on the span, never silent.
        if is_auxiliary_request(
            body,
            utility_models=settings.utility_models,
            enabled=settings.filter_auxiliary_requests,
        ):
            _tracer.set_attrs({"url4.classified": "auxiliary", "url4.aux_model": model})
            logger.info(
                "[E2E-TRACE] PROXY classified AUX (model=%s) → synthetic, no /ensemble | stream=%s",
                model,
                is_streaming,
            )
            if is_streaming:
                return StreamingResponse(
                    stream_anthropic_sse(AUX_STUB_TEXT, model, prompt_text=""),
                    media_type="text/event-stream",
                )
            return JSONResponse(
                content=build_anthropic_message(AUX_STUB_TEXT, model, prompt_text=""),
                status_code=200,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the claude_frontend suite to confirm no regressions**

Run: `uv run pytest -q -m "not live" src/screamingface/plugins/claude_frontend/`
Expected: PASS — existing proxy/terminal tests use Opus/Sonnet models and carry CC identity, so they resolve via /ensemble exactly as before.

- [ ] **Step 6: Commit**

```bash
git add src/screamingface/plugins/claude_frontend/proxy.py src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py
git commit -m "feat(claude-frontend): route utility-model aux requests to synthetic, skip /ensemble (SF-241)"
```

---

## Task 4: Full gate + types + pre-commit + PR

**Files:** none (verification task)

- [ ] **Step 1: Types** — `cd apps/server && uv run pyright` → 0 errors. (Editor `reportMissingImports` for `screamingface.*` are false positives without the server venv — trust `uv run pyright`.)

- [ ] **Step 2: Full non-live suite (mirror CI)** — `cd apps/server && uv run pytest -q -m "not live" tests/ src/screamingface/plugins/` → PASS. This is the real gate; the `tests/e2e/` claude_frontend tests must still pass.

- [ ] **Step 3: Pre-commit** — `pre-commit run --files src/screamingface/plugins/claude_frontend/_classifier.py src/screamingface/plugins/claude_frontend/plugin.py src/screamingface/plugins/claude_frontend/proxy.py src/screamingface/plugins/claude_frontend/tests/test_classifier.py src/screamingface/plugins/claude_frontend/tests/test_proxy_aux_filter.py` → PASS. If `ruff-format` reformats, re-stage and amend the relevant commit.

- [ ] **Step 4: Open PR** via superpowers:finishing-a-development-branch. Body references SF-241, summarizes the bug + the utility-model→synthetic fix + the R0 main-loop safety override. **Do NOT merge** — Sergey reviews & merges.

---

## Residual risk / follow-ups (not blocking)

- **Empty stub for `isNewTopic`/title-gen:** correct for header-only probes (the observed "quota" case); cosmetic for title/topic per the taxonomy. If a future CC version `json.loads(content[0].text)` without try/except, an empty body could surface a visible (non-data-loss) glitch — smoke-test a live `claude` binary and, if needed, emit minimal valid JSON for those signatures. Tracked as a follow-up, not v1-blocking.
- **Recall of non-Haiku aux calls:** if Anthropic ever routes an aux task to Sonnet/Opus, it falls through to `/ensemble` (safe direction — extra cost, never a dropped prompt).
- **Stale doc:** `secondbrain/.../docs/plugins/claude-frontend.md` still describes the pre-terminal forwarding model; refresh separately.

---

## Self-Review

**Spec coverage:** "only user prompts reach /ensemble" → Task 3 gate (aux returns before resolution; Task 3 Step 5 regression). "Utility-model → synthetic" → Tasks 1–3. "Never drop a real user prompt" → R0 override (`test_haiku_MAIN_LOOP_turn_is_NOT_auxiliary`, `test_haiku_main_loop_turn_reaches_ensemble`) + configurable allowlist. "Fail-loud" → span attr + INFO log on every aux decision. ✓

**Placeholder scan:** No TODO/"handle edge cases"; concrete code + commands throughout. ✓

**Type consistency:** `is_auxiliary_request(body, *, utility_models: list[str], enabled: bool) -> bool`, `is_cc_main_loop(body) -> bool`, `is_utility_model(model: str, utility_models: list[str]) -> bool`, `AUX_STUB_TEXT: str` — used identically across `_classifier.py`, `proxy.py`, and both test files. Settings `filter_auxiliary_requests: bool` / `utility_models: list[str]` match across plugin.py and tests. ✓
