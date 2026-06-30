"""SF-290: a backend call's context args that are fetchable refs (``/...`` or
``http(s)://...``) must be FETCHED before reaching LLM backends — while
``/python``-style backends still receive the raw path (they fetch it
themselves). Comma-containing text and JSON blobs must pass through unchanged.
"""

from __future__ import annotations

import pytest

from screamingface.plugins.url4_executor import url4_resolve as ur
from screamingface.plugins.url4_executor.tests.test_ensemble import (
    _FakeDispatchPlugin,
    _make_app,
)
from screamingface.plugins.url4_executor.url4 import Url4BackendCall, Url4Text

# ---------------------------------------------------------------------------
# _resolve_context_sources — splitting + per-segment fetch
# ---------------------------------------------------------------------------


async def test_resolve_fetches_relative_ref_and_preserves_comma_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_rel(app: object, path: str) -> str:
        return f"<doc:{path}>"

    monkeypatch.setattr(ur, "_fetch_relative", fake_rel)
    # A question with embedded commas + a trailing /private path (the SF-290 case).
    src = "Screenwriter, director, stronger., /private/abc"
    out = await ur._resolve_context_sources(src, app=object(), env=None)
    assert out == "Screenwriter, director, stronger.,<doc:/private/abc>"


async def test_resolve_passthrough_text_and_json() -> None:
    # No fetchable segment → unchanged (comma-containing prose).
    assert (
        await ur._resolve_context_sources("What is 2+2? answer: 4, right!", app=None, env=None)
        == "What is 2+2? answer: 4, right!"
    )
    # JSON blob with commas, no leading-slash segment → unchanged.
    assert (
        await ur._resolve_context_sources('{"a":1, "b":2}', app=None, env=None) == '{"a":1, "b":2}'
    )


async def test_resolve_fetches_http_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_url(url: str) -> str:
        return f"<url:{url}>"

    monkeypatch.setattr(ur, "_fetch_url", fake_url)
    out = await ur._resolve_context_sources("intro, https://x.com/doc", app=None, env=None)
    assert out == "intro,<url:https://x.com/doc>"


async def test_resolve_empty_and_none() -> None:
    assert await ur._resolve_context_sources("", app=None, env=None) == ""
    assert await ur._resolve_context_sources(None, app=None, env=None) == ""


# ---------------------------------------------------------------------------
# _dispatch_backend_call — resolution gated on the plugin opt-in flag
# ---------------------------------------------------------------------------


class _LlmPlugin(_FakeDispatchPlugin):
    """LLM-style backend: wants context refs pre-fetched."""

    resolves_context_sources = True


async def test_dispatch_resolves_context_for_llm_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_rel(app: object, path: str) -> str:
        return "DOC-BODY"

    monkeypatch.setattr(ur, "_fetch_relative", fake_rel)
    plugin = _LlmPlugin("claude-backend-api", ["/claude"], "ok")
    app = _make_app(plugin)
    node = Url4BackendCall(
        path="/claude",
        packed_context="q text, /private/abc",
        intent=Url4Text(value="answer"),
    )

    await ur._dispatch_backend_call(node, app, None)

    _intent, sources, _app = plugin.calls[0]
    assert sources == "q text,DOC-BODY"


async def test_dispatch_passes_raw_path_for_non_opted_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/python-style backend (no opt-in flag) receives the raw path — it does
    its own fetching, so pre-fetching here would break it."""

    async def fake_rel(app: object, path: str) -> str:
        raise AssertionError("context must NOT be fetched for a non-opted backend")

    monkeypatch.setattr(ur, "_fetch_relative", fake_rel)
    plugin = _FakeDispatchPlugin("python-runner", ["/python"], "{}")
    app = _make_app(plugin)
    node = Url4BackendCall(
        path="/python",
        packed_context="/data/code/check.py",
        intent=Url4Text(value="{}"),
    )

    await ur._dispatch_backend_call(node, app, None)

    _intent, sources, _app = plugin.calls[0]
    assert sources == "/data/code/check.py"


# ---------------------------------------------------------------------------
# Offline e2e: real /ensemble route + real in-process /private fetch (no network)
# ---------------------------------------------------------------------------

import httpx  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402

from screamingface.core.app import create_app  # noqa: E402
from screamingface.core.config import AppConfig  # noqa: E402


@pytest.fixture
async def app_url4():
    app = create_app(AppConfig(plugins=["url4-executor"], plugin_config={}))
    async with app.router.lifespan_context(app):
        yield app


def _inject(app, *plugins) -> None:
    # active_plugins is a copy; mutate the backing _active dict.
    for p in plugins:
        app.state.plugins._active[p.name] = p


async def _ensemble(app, q: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost", timeout=60) as c:
        return await c.get("/ensemble", params={"q": q})


class _EchoLlmPlugin:
    """LLM-style backend that echoes the context it received (opts into fetch)."""

    name = "claude-backend-api"
    backend_call_paths = ["/claude"]
    resolves_context_sources = True

    def __init__(self) -> None:
        self.last_sources: str | None = None

    async def handle_backend_call(self, intent, *, sources="", app, env=None) -> str:
        del intent, app, env
        self.last_sources = sources
        return f"ECHO::{sources}"


class _RawLocatorPlugin:
    """/python-style backend that must receive the RAW locator (no opt-in)."""

    name = "python-runner"
    backend_call_paths = ["/python"]

    def __init__(self) -> None:
        self.last_sources: str | None = None

    async def handle_backend_call(self, intent, *, sources="", app, env=None) -> str:
        del intent, app, env
        self.last_sources = sources
        return "{}"


@pytest.mark.asyncio
async def test_e2e_offline_llm_backend_fetches_private_context_path(app_url4) -> None:
    """Offline e2e: a /private context ref is fetched in-process (ASGI, no
    network) and its content — not the path string — reaches the LLM backend."""

    async def private_doc(pid: str) -> PlainTextResponse:
        return PlainTextResponse(f"PRIVATE-DOC[{pid}]")

    app_url4.add_api_route("/private/{pid}", private_doc, methods=["GET"])
    llm = _EchoLlmPlugin()
    _inject(app_url4, llm)

    # Context with a comma-containing question AND a fetchable /private path.
    resp = await _ensemble(app_url4, "/claude(Who, what, /private/abc123)!answer")

    assert resp.status_code == 200, resp.text
    assert llm.last_sources is not None
    assert "PRIVATE-DOC[abc123]" in llm.last_sources  # fetched content present
    assert "/private/abc123" not in llm.last_sources  # raw path gone
    assert "Who, what" in llm.last_sources  # comma text preserved verbatim


@pytest.mark.asyncio
async def test_e2e_offline_llm_backend_normalizes_repeated_leading_slashes(
    app_url4,
) -> None:
    async def private_doc(pid: str) -> PlainTextResponse:
        return PlainTextResponse(f"PRIVATE-DOC[{pid}]")

    async def wrong_doc() -> PlainTextResponse:
        return PlainTextResponse("WRONG-DOC")

    app_url4.add_api_route("/private/{pid}", private_doc, methods=["GET"])
    app_url4.add_api_route("/abc123", wrong_doc, methods=["GET"])
    llm = _EchoLlmPlugin()
    _inject(app_url4, llm)

    resp = await _ensemble(app_url4, "/claude(Who, what, //private/abc123)!answer")

    assert resp.status_code == 200, resp.text
    assert llm.last_sources is not None
    assert "PRIVATE-DOC[abc123]" in llm.last_sources
    assert "WRONG-DOC" not in llm.last_sources
    assert "//private/abc123" not in llm.last_sources


@pytest.mark.asyncio
async def test_e2e_offline_python_backend_keeps_raw_locator(app_url4) -> None:
    """Offline e2e: a /python backend (no opt-in) still receives the raw
    locator path — the dispatcher must NOT pre-fetch it."""
    raw = _RawLocatorPlugin()
    _inject(app_url4, raw)

    resp = await _ensemble(app_url4, "/python(/data/code/check.py)!{}")

    assert resp.status_code == 200, resp.text
    assert raw.last_sources == "/data/code/check.py"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
