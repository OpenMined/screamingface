from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine import catalog, cli


def test_model_catalog_is_unique_and_does_not_claim_unimplemented_tools() -> None:
    registry = catalog.registry_document(MODEL_ROUTES)

    assert len({model.id for model in MODEL_ROUTES}) == len(MODEL_ROUTES)
    assert len({model.route for model in MODEL_ROUTES}) == len(MODEL_ROUTES)
    assert all(model.gateway_model for model in MODEL_ROUTES)
    assert registry == {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [
            {
                "id": provider.id,
                "display_name": provider.display_name,
                "auth_methods": list(provider.auth_methods),
            }
            for provider in catalog.PUBLIC_PROVIDERS
        ],
        "models": [
            {"id": model.id, "provider": model.provider, "supported_tools": []}
            for model in MODEL_ROUTES
        ],
        "benchmarks": [benchmark.public for benchmark in catalog.BENCHMARK_ROUTES],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote/1"}],
    }


def test_cli_serves_configured_host_port_and_h11_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, str, int, int, bool]] = []
    app = object()

    def capture(value, *, host, port, h11_max_incomplete_event_size, access_log) -> None:
        calls.append((value, host, port, h11_max_incomplete_event_size, access_log))

    run = Mock(side_effect=capture)
    monkeypatch.setattr(cli, "create_app", lambda *, settings: app)
    monkeypatch.setattr(cli.importlib, "import_module", lambda _name: SimpleNamespace(run=run))
    monkeypatch.setenv("URL4_HOST", "0.0.0.0")
    monkeypatch.setenv("URL4_PORT", "4500")

    cli.main()

    assert calls == [(app, "0.0.0.0", 4500, 131072, False)]
