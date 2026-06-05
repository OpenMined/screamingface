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
    (case-insensitive). A non-string/empty ``model`` or empty ``utility_models``
    → False. The non-string guard matters because the classifier runs on the raw,
    unvalidated request body, so a malformed ``"model": 123`` must fall through to
    the safe /ensemble direction rather than raise.
    """
    if not isinstance(model, str) or not model or not utility_models:
        return False
    lowered = model.lower()
    return any(u.lower() in lowered for u in utility_models)


def is_auxiliary_request(body: dict[str, Any], *, utility_models: list[str], enabled: bool) -> bool:
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
