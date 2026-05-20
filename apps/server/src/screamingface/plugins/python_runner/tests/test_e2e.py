"""End-to-end test: URL4 backend call -> /python -> /data/code/{name}.py -> run.

In-process via httpx ASGI transport; no live server, no network. Sandbox
is active on darwin (SF-158).

Notes for reviewers (URL4 entry point + syntax choice):

* Entry point: ``GET /ensemble?q=<url4>`` -- the standard URL4 resolution
  surface. See ``apps/server/tests/e2e/test_url4_resolution.py`` for the
  live-server analog; here we drive the same handler in-process through
  ``httpx.ASGITransport`` so we exercise the full FastAPI stack
  (middleware, routing, plugin dispatch, in-process ``/data/code/...``
  fetch) without spawning a server.

* URL4 syntax: ``(/python(/data/code/echo.py)!{"x":1})``. The outer
  parens are load-bearing -- ``EnsembleInterpreter`` calls
  ``split_intent`` on the *top-level* expression and would strip the
  ``!{"x":1}`` off as an ensemble intent (joined to the dispatch result
  with ``\n\n``) instead of feeding it to the backend call. Wrapping
  the whole thing in a group makes it a single atom, so ``split_intent``
  doesn't fire and the inner backend_call keeps its own intent. The
  grammar's intent ``text`` atom matches ``[^,()]+``, so the JSON must
  avoid commas/parens; the single-key form ``{"x":1}`` is enough to
  round-trip the payload here.

* Active plugins: we activate ``url4-executor`` (for ``/ensemble``) and
  ``python-runner`` (which registers ``/data/code/{name}.py`` plus the
  ``/python`` backend dispatch path) via ``AppConfig``. Scripts are
  injected by replacing the plugin's ``settings`` post-activation,
  mirroring ``test_plugin_dispatch.py``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.python_runner.plugin import PythonRunnerSettings

ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"echoed": data}))
"""


@pytest.mark.asyncio
async def test_e2e_url4_dispatch_to_python_runner() -> None:
    config = AppConfig(plugins=["url4-executor", "python-runner"], plugin_config={})
    app = create_app(config)

    # Inject a deterministic script via settings (same pattern as
    # test_plugin_dispatch.py); avoids depending on vendored defaults.
    plugin = app.state.plugins.active_plugins["python-runner"]
    plugin.settings = PythonRunnerSettings(scripts={"echo": ECHO_SCRIPT})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=60
    ) as client:
        url4 = '(/python(/data/code/echo.py)!{"x":1})'
        resp = await client.get("/ensemble", params={"q": url4})

    assert resp.status_code == 200, resp.text

    # /ensemble returns the resolved URL4 string as text/plain. For a
    # backend_call node that's exactly what the plugin returned -- a JSON
    # string from ``handle_backend_call``. Parse it and verify the
    # script's output round-tripped through the URL4 layer.
    payload = json.loads(resp.text)
    assert payload == {"echoed": {"x": 1}}
