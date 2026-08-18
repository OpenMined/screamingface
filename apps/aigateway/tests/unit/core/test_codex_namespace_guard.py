"""Named routing regression guard for the two independent OpenAI-family providers.

FEATURE: provider-namespace routing. Codex serves OpenAI-FAMILY GPT models (``gpt-5.x``)
over the ChatGPT *subscription* endpoint. They MUST surface under the ``codex`` namespace
and resolve back to the codex plugin. Direct OpenAI Platform API-key models MUST surface
under the separate ``openai`` namespace and resolve back to that plugin. The same upstream
model name can intentionally exist in both namespaces without either owner capturing it.

STORY: as a gateway maintainer, I get a named, greppable alarm if anyone ever introduces an
OpenAI-family model such that its canonical namespace stops resolving to the credential and
endpoint owner selected by the caller.

INVARIANT: every model's canonical id starts with its owner's distinct registry key and its
first path segment resolves to that same plugin, even when the bare upstream names overlap.
This is the ONE place provider names are domain-correct assertions rather than a central
inventory; the provider-agnostic form still lives in ``test_provider_contract_conformance.py``.
"""

from __future__ import annotations

from aigateway.core.loader import load_plugins
from aigateway.core.model_capabilities import canonical_model_id
from aigateway.core.registry import ProviderRegistry


def test_codex_and_direct_openai_models_keep_independent_namespaces() -> None:
    registry = ProviderRegistry()
    load_plugins(registry)

    codex = registry.get("codex")
    openai = registry.get("openai")
    assert codex is not None
    assert openai is not None
    assert codex is not openai

    for owner in (codex, openai):
        for entry in owner.register_models():
            canonical = canonical_model_id(
                custom_llm_provider=owner.custom_llm_provider,
                model_name=entry.model_name,
            )
            assert canonical.startswith(f"{owner.custom_llm_provider}/"), canonical
            assert registry.get(canonical.split("/", 1)[0]) is owner, canonical

    codex_upstream = {entry.model_name.split("/", 1)[-1] for entry in codex.register_models()}
    openai_upstream = {entry.model_name.split("/", 1)[-1] for entry in openai.register_models()}
    assert codex_upstream & openai_upstream, "the overlap guard must exercise a shared model name"
