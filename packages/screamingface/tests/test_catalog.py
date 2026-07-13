"""sf.models — the catalog service (list / get).

FEATURE: model discovery — step 2 of the quickstart (connect → pick → compose → run).
The prototype's `sf.models` was a Pool (both service and collection); the SDK makes it
a thin service returning plain `provider/model` id strings (API_STRUCTURE.md §5).
"""

from __future__ import annotations

import pytest

import screamingface as sf


class TestList:
    def test_returns_provider_model_ids(self):
        ids = sf.models.list()
        assert ids, "catalog must not be empty"
        assert all(isinstance(i, str) and "/" in i for i in ids)

    def test_max_price_filters_combined_price(self):
        # WHY: `price` is in+out per M tokens (matches the prototype/studio semantics).
        ids = sf.models.list(max_price=20)
        assert ids
        for i in ids:
            m = sf.models.get(i)
            assert m.price <= 20

    def test_max_price_excludes_expensive_models(self):
        all_ids = set(sf.models.list())
        cheap = set(sf.models.list(max_price=20))
        assert cheap < all_ids  # something got excluded
        # the quickstart's exemplar expensive model
        assert "open_router/claude-opus-4" in all_ids - cheap

    def test_search_matches_name_substring(self):
        ids = sf.models.list(search="claude")
        assert ids
        assert all("claude" in i.split("/", 1)[1] for i in ids)

    def test_provider_filter_accepts_slug(self):
        ids = sf.models.list(provider="google")
        assert ids
        assert all(i.startswith("google/") for i in ids)

    @pytest.mark.parametrize("sort_key", ["price", "context", "ability", "name"])
    def test_sort_keys(self, sort_key):
        ids = sf.models.list(sort=sort_key)
        assert ids == sorted(
            ids,
            key=lambda i: getattr(
                sf.models.get(i),
                {"price": "price", "context": "ctx", "ability": "ability", "name": "name"}[
                    sort_key
                ],
            ),
            reverse=sort_key in ("ability", "context"),  # WHY: desc defaults for these
        )

    def test_min_ctx_filter(self):
        ids = sf.models.list(min_ctx=1_000_000)
        assert ids
        assert all(sf.models.get(i).ctx >= 1_000_000 for i in ids)


class TestGet:
    def test_get_returns_model_card(self):
        m = sf.models.get("anthropic/claude-opus-4.8")
        assert m.name == "Claude Opus 4.8"
        assert m.provider_name == "Anthropic"
        assert m.price_in > 0 and m.price_out > 0 and m.ctx > 0

    def test_get_accepts_owner_prefixed_id(self):
        # WHY: owner/provider/model is the federation seam; local owner is implied.
        assert (
            sf.models.get("local/anthropic/claude-opus-4.8").id
            == sf.models.get("anthropic/claude-opus-4.8").id
        )

    def test_get_unknown_raises_keyerror_with_hint(self):
        with pytest.raises(KeyError, match="models.list"):
            sf.models.get("nope/does-not-exist")
