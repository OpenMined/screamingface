"""SF-236 / WI-2: collected errors must be visible to the caller.

When a collection runs with ``;foreach.on_error=collect``, per-row
exceptions are caught and turned into ``{"error": ...}`` JSON elements
instead of aborting the run (HTTP stays 200). Before this change nothing
signalled to the caller that errors had been collected. We now surface
the count on:

- the ``url4.collection_iterate`` span (attribute
  ``url4.collection.errors_collected``), and
- an HTTP response header ``X-SF-Collected-Errors`` on ``/ensemble``.

These tests drive the real ``/ensemble`` route in-process via
``httpx.ASGITransport`` (modelled on ``eval_runs`` e2e tests), injecting
fake backend plugins into ``app.state.plugins.active_plugins`` (modelled
on the fan-out failure tests). One fake plugin serves the collection
JSON array; another evaluates each row and RAISES for one specific item.
"""

from __future__ import annotations

import httpx
import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter


class _DataPlugin:
    """Serves the collection source: returns its packed context verbatim.

    The collection source ``/data([1, 2, 3])`` carries the JSON array as
    its packed context, which ``handle_backend_call`` receives as
    ``sources`` and echoes back so ``parse_collection`` can split it.
    """

    name = "data"
    backend_call_paths = ["/data"]

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del intent, app, env
        return sources


class _FailOnTwoPlugin:
    """Per-row evaluator that raises for item ``2`` and succeeds otherwise."""

    name = "x"
    backend_call_paths = ["/x"]

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del intent, app, env
        if sources == "2":
            raise RuntimeError("boom")
        return f"ok-{sources}"


def _inject(app, *plugins) -> None:
    # ``active_plugins`` is a property returning a COPY; mutate the backing
    # ``_active`` dict so the route's plugin lookup actually sees the fakes.
    for p in plugins:
        app.state.plugins._active[p.name] = p


@pytest.fixture
async def app_url4():
    config = AppConfig(plugins=["url4-executor"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


async def _get(app, q: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        return await c.get("/ensemble", params={"q": q})


@pytest.mark.asyncio
async def test_collected_errors_header_set_when_one_row_errors(app_url4) -> None:
    _inject(app_url4, _DataPlugin(), _FailOnTwoPlugin())
    # Collection source is a backend call returning the array; row 2 raises.
    q = "/data([1, 2, 3])*(/x($item)) ;foreach.on_error=collect"

    resp = await _get(app_url4, q)

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-SF-Collected-Errors"] == "1"


@pytest.mark.asyncio
async def test_no_header_when_no_errors(app_url4) -> None:
    class _AlwaysOkPlugin:
        name = "x"
        backend_call_paths = ["/x"]

        async def handle_backend_call(self, intent, *, sources="", app, env=None):
            del intent, app, env
            return f"ok-{sources}"

    _inject(app_url4, _DataPlugin(), _AlwaysOkPlugin())
    q = "/data([1, 2, 3])*(/x($item)) ;foreach.on_error=collect"

    resp = await _get(app_url4, q)

    assert resp.status_code == 200, resp.text
    assert "X-SF-Collected-Errors" not in resp.headers


def test_collected_error_payload_nonempty_message_and_traceback() -> None:
    """SF-286: a collected error must be diagnosable even when the exception
    carries no message (e.g. a bare ``NotImplementedError`` from TatSu's parse
    engine). Before this, the payload was ``{"kind": "...", "message": ""}`` —
    opaque. Now: a repr fallback for the message + a captured traceback tail.
    """
    from screamingface.plugins.url4_executor.ensemble import _collected_error_payload

    def _raises_bare() -> None:
        raise NotImplementedError  # bare: str(exc) == ""

    try:
        _raises_bare()
    except NotImplementedError as exc:
        payload = _collected_error_payload(exc)

    err = payload["error"]
    assert err["kind"] == "NotImplementedError"
    # message is non-empty: repr fallback when str(exc) is blank.
    assert err["message"]
    assert "NotImplementedError" in err["message"]
    # traceback names the raising frame so the origin is locatable.
    assert "_raises_bare" in err["traceback"]
    assert "NotImplementedError" in err["traceback"]


class _RaiseBarePlugin:
    """Per-row evaluator that raises a bare (message-less) NotImplementedError
    for item ``2`` — mirrors the TatSu parse-engine failure mode."""

    name = "x"
    backend_call_paths = ["/x"]

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del intent, app, env
        if sources == "2":
            raise NotImplementedError
        return f"ok-{sources}"


@pytest.mark.asyncio
async def test_collected_empty_message_error_is_diagnosable_in_body(app_url4) -> None:
    """End-to-end: a message-less per-row exception surfaces in the response
    body with a kind, a non-empty message, and a traceback — not an empty
    ``NotImplementedError``."""
    import json

    _inject(app_url4, _DataPlugin(), _RaiseBarePlugin())
    q = "/data([1, 2, 3])*(/x($item)) ;foreach.on_error=collect"

    resp = await _get(app_url4, q)

    assert resp.status_code == 200, resp.text
    assert resp.headers["X-SF-Collected-Errors"] == "1"
    # The errored row's JSON object is embedded in the response body.
    assert '"kind": "NotImplementedError"' in resp.text
    assert '"message": ""' not in resp.text  # no opaque empty-message errors
    payload = json.loads(resp.text) if resp.text.startswith("[") else None
    del payload  # body shape is route-defined; substring checks above suffice


@pytest.mark.asyncio
async def test_interpreter_accumulates_collected_errors_count() -> None:
    """Focused unit check: the interpreter counts collected errors and the
    count survives on the (per-request) interpreter instance.
    """
    from screamingface.plugins.url4_executor.tests.test_ensemble import _make_app

    app = _make_app(_DataPlugin(), _FailOnTwoPlugin())  # pyright: ignore[reportArgumentType]
    interp = EnsembleInterpreter(app=app)
    assert interp._collected_errors == 0  # initialized in __init__

    await interp.evaluate("/data([1, 2, 3])*(/x($item)) ;foreach.on_error=collect")
    assert interp._collected_errors == 1
