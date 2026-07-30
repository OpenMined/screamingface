"""Phase 10 (OME-479 §Phase 10): the ONE legitimately-named routing regression guard.

FEATURE: provider-namespace routing. Codex serves OpenAI-FAMILY GPT models (``gpt-5.x``)
over the ChatGPT *subscription* endpoint. They MUST surface under the ``codex`` namespace
and resolve back to the codex plugin — NEVER under a separate ``openai`` provider that
would capture the same GPT-family ids and split dispatch across two owners.

STORY: as a gateway maintainer, I get a named, greppable alarm if anyone ever introduces an
``openai`` provider (or renames codex) such that ``codex/gpt-5.x`` ids stop routing to the
codex plugin — the exact historical sharp edge this contract was built to prevent.

INVARIANT: ``registry.get("openai") is None`` (nothing captures the GPT-family ids) AND every
codex model's canonical id is ``codex/…`` whose first path segment resolves to the codex
plugin. This is the ONE place a provider name is a domain-correct assertion rather than a
central inventory — the provider-AGNOSTIC version of this guarantee (proven for EVERY model,
current and future) lives in ``test_provider_contract_conformance.py``. Keeping the named
guard in its own codex-dedicated file (never appended to a committed test file) satisfies the
append-only gate, which admits new test files but flags any edit to an existing one.
"""

from __future__ import annotations

from aigateway.core.loader import load_plugins
from aigateway.core.model_capabilities import canonical_model_id
from aigateway.core.registry import ProviderRegistry


def test_codex_models_stay_under_codex_namespace_never_openai() -> None:
    registry = ProviderRegistry()
    load_plugins(registry)

    codex = registry.get("codex")
    assert codex is not None
    # No `openai` provider may exist to capture the GPT-family ids codex owns.
    assert registry.get("openai") is None

    for entry in codex.register_models():
        canonical = canonical_model_id(custom_llm_provider="codex", model_name=entry.model_name)
        # WHY: the canonical id's first segment IS the owning plugin's registry key, so a
        # GPT-family id that resolved anywhere but codex would fail here (fail-closed routing).
        assert canonical.startswith("codex/"), canonical
        assert registry.get(canonical.split("/", 1)[0]) is codex, canonical
