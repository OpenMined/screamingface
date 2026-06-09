"""SF-246: no-auth dispatch backends (e.g. python-runner) must be excluded from
the credential/health status walk.

``backend_call_paths`` is overloaded — it marks a plugin as a url4 backend-call
target AND was the sole gate for inclusion in ``/backends/status``. A runner
like python-runner has a dispatch path (``/python``) but no credentials and no
``/health`` route, so it was probed, 404'd, and reported as
"Credential is missing or expired." Plugins set ``requires_auth = False`` to opt
out of the credential status walk.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from screamingface.plugins.llm_base import routes as status_routes


class _CredentialedBackend:
    name = "claude-backend-api"
    backend_call_paths = ["/claude"]
    # requires_auth not set → defaults to True (credentialed backend)


class _NoAuthRunner:
    name = "python-runner"
    backend_call_paths = ["/python"]
    requires_auth = False


@pytest.mark.anyio
async def test_collect_backend_status_skips_no_auth_runner(monkeypatch) -> None:
    async def fake_probe(_base_url: str, _name: str) -> dict[str, object]:
        # Simulate a plugin with no /health route (python-runner): 404 → unauthenticated.
        return {"authenticated": False, "error": "no health endpoint"}

    monkeypatch.setattr(status_routes, "_probe_health", fake_probe)
    monkeypatch.setattr(status_routes, "_get_base_url", lambda _app: "http://test")

    app = SimpleNamespace(
        state=SimpleNamespace(
            plugins=SimpleNamespace(
                active_plugins={
                    "claude-backend-api": _CredentialedBackend(),
                    "python-runner": _NoAuthRunner(),
                }
            )
        )
    )

    result = await status_routes._collect_backend_status(app)

    # The credentialed backend is still reported (and would surface reauth).
    assert "claude" in result
    # The no-auth runner is excluded entirely — never classified reauth.
    assert "python" not in result
