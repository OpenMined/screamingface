"""Session — provider connections and key safety.

INVARIANT (spec I4): keys live only in the in-process KeyStore; never echoed,
never in reprs, at most masked to the last 4 characters.
"""

from __future__ import annotations

import pytest

import screamingface as sf
from screamingface.session import Session, _mask


@pytest.fixture
def fresh() -> Session:
    return Session()


class TestConnect:
    def test_connect_from_env_var(self, fresh, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-abcd1234")
        conn = fresh.connect("anthropic")
        assert conn.connected
        assert conn.source == "env"
        assert fresh.is_connected("anthropic")

    def test_connect_with_explicit_key(self, fresh):
        conn = fresh.connect("openai", api_key="sk-direct")
        assert conn.connected and conn.source == "entered"

    def test_connect_accepts_studio_slug(self, fresh):
        # WHY: notebooks say sf.connect("google"); the engine provider id is "deepmind".
        conn = fresh.connect("google", api_key="k")
        assert conn.provider_id == "deepmind"

    def test_missing_key_raises_with_env_hint(self, fresh, monkeypatch):
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        with pytest.raises(ValueError, match="PERPLEXITY_API_KEY"):
            fresh.connect("perplexity", prompt=False)

    def test_unknown_provider_raises(self, fresh):
        with pytest.raises(KeyError, match="[Uu]nknown provider"):
            fresh.connect("skynet")


class TestKeySafety:
    def test_status_rows_mask_keys(self, fresh):
        fresh.connect("anthropic", api_key="sk-test-abcd1234")
        rows = {r["provider"]: r for r in fresh.status_rows()}
        shown = rows["Anthropic"]["key"]
        assert "sk-test" not in shown
        assert shown.endswith("1234") and shown.startswith("…")

    def test_mask_never_reveals_short_keys(self):
        assert _mask("abc") == "…"
        assert _mask("") == ""

    def test_key_not_in_any_row_field(self, fresh):
        # INVARIANT I4 — sweep every surface the status view exposes.
        secret = "sk-test-abcd1234"
        fresh.connect("anthropic", api_key=secret)
        for row in fresh.status_rows():
            for v in row.values():
                assert secret not in str(v)


class TestSetupHeadless:
    def test_setup_prints_instructions_outside_notebooks(self, capsys):
        result = sf.setup()
        assert result is None
        out = capsys.readouterr().out
        assert "sf.connect" in out
