"""Smoke import test for BaseStore — full behaviour is exercised in test_plugin.py."""

from __future__ import annotations

from screamingface.plugins.state.store import BaseStore


def test_basestore_requires_model() -> None:
    import pytest

    class _Bad(BaseStore):
        pass

    with pytest.raises(TypeError, match="must set `model`"):
        _Bad()
