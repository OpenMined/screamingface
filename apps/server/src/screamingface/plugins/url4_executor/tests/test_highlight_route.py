"""Regression tests for the /ensemble/highlight route used by Url4Viewer.tsx.

Earlier the renderer (apps/desktop/src/renderer/src/components/Url4Viewer.tsx)
called ``GET {sfBase}/url4/highlight?q=<expr>`` but the server only mounted
``/ensemble/highlight``, so the renderer logged
``[Url4Viewer] highlight request failed: 404 undefined``. The renderer is now
aligned with the canonical ``/ensemble/highlight`` path; these tests pin both
sides of that contract: the route exists, behaves correctly, and the legacy
``/url4/highlight`` path is NOT mounted (so any new caller using it gets a
proper 404 rather than depending on an undocumented alias).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.url4_executor.routes import create_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router(app=app))
    return TestClient(app)


def test_ensemble_highlight_returns_tokens() -> None:
    client = _client()
    resp = client.get("/ensemble/highlight", params={"q": "https://example.com/api"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("tokens"), list)
    assert body["tokens"], "tokens list should be non-empty for a valid expression"


def test_ensemble_highlight_handles_paren_list() -> None:
    client = _client()
    resp = client.get(
        "/ensemble/highlight", params={"q": "(http://a.com, hello)"}
    )
    assert resp.status_code == 200
    tokens = resp.json()["tokens"]
    types = [t["type"] for t in tokens]
    assert "paren" in types
    assert "url" in types


def test_ensemble_highlight_missing_q_returns_400() -> None:
    client = _client()
    resp = client.get("/ensemble/highlight")
    assert resp.status_code == 400


def test_ensemble_highlight_invalid_expression_returns_400() -> None:
    client = _client()
    # Unbalanced parens — must surface as a 400, not a 500.
    resp = client.get("/ensemble/highlight", params={"q": "(unclosed"})
    assert resp.status_code == 400


def test_url4_highlight_path_is_not_mounted() -> None:
    """No /url4/* routes — the renderer must use /ensemble/highlight.

    Pinning this prevents accidental re-introduction of an alias path that
    nothing in the codebase actually wants.
    """
    client = _client()
    resp = client.get("/url4/highlight", params={"q": "https://example.com"})
    assert resp.status_code == 404
