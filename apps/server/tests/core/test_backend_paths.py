from __future__ import annotations

import logging

from screamingface.core.backend_paths import catalog_aliases_from_model_ids


def test_catalog_aliases_are_independent_of_model_order_for_numeric_collisions() -> None:
    ids = ["codex/gpt-5.4-mini", "codex/gpt-5-4-mini"]

    assert catalog_aliases_from_model_ids(ids) == catalog_aliases_from_model_ids(
        list(reversed(ids))
    )


def test_catalog_aliases_hash_true_slug_collisions_and_warn(caplog) -> None:
    ids = ["codex/gpt-5.4-mini", "codex/gpt-5-4-mini"]

    with caplog.at_level(logging.WARNING, logger="screamingface.core.backend_paths"):
        aliases = catalog_aliases_from_model_ids(ids)

    assert "gpt-5-4-mini" not in aliases
    assert "gpt-5-4-mini-2" not in aliases
    assert sorted(aliases.values()) == sorted(ids)
    assert all(alias.startswith("gpt-5-4-mini-") for alias in aliases)
    assert "catalog model alias collision" in caplog.text


def test_catalog_aliases_disambiguate_owner_only_collisions_stably() -> None:
    ids = ["huggingface/openai/model", "huggingface/meta/model"]

    aliases = catalog_aliases_from_model_ids(list(reversed(ids)))

    assert aliases == {
        "model-meta": "huggingface/meta/model",
        "model-openai": "huggingface/openai/model",
    }


def test_catalog_aliases_drop_empty_inputs_and_empty_slugs() -> None:
    assert catalog_aliases_from_model_ids([]) == {}
    assert catalog_aliases_from_model_ids(["", "/", "huggingface/!!!"]) == {}


def test_catalog_aliases_dedupe_identical_model_ids() -> None:
    assert catalog_aliases_from_model_ids(["codex/gpt-5.4", "codex/gpt-5.4"]) == {
        "gpt-5-4": "codex/gpt-5.4"
    }
