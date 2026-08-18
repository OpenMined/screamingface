"""The `requests` counter must be labeled by ROUTE TEMPLATE, never by the raw request path.

STORY (C4): `MetricsMiddleware` wraps the whole ASGI app, so every unrouted request still emits
`http.response.start` and mints a permanent `Counter` child. Labeled with `scope["path"]`, an
unauthenticated caller walking `/aaaa1`, `/aaaa2`, ... grows the registry without bound and it is
never evicted — a remote OOM against a `replicaCount: 1` control plane, reachable without a
credential because `POST /token` needs none. Labeled with the matched route template the label set
is finite: one entry per registered route plus `<unmatched>`.
"""

from prometheus_client import CollectorRegistry
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from screamingface_engine.metrics import UNMATCHED_PATH, MetricsMiddleware, build_metrics


def _label_values(registry: CollectorRegistry) -> set[str]:
    return {
        sample.labels["path"]
        for metric in registry.collect()
        for sample in metric.samples
        if "path" in sample.labels
    }


def _app() -> tuple[Starlette, object]:
    async def ok(request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/things/{thing_id}", ok)])
    app.add_middleware(MetricsMiddleware)
    metrics = build_metrics()
    app.state.metrics = metrics
    return app, metrics


def test_unmatched_paths_all_collapse_onto_one_label() -> None:
    app, metrics = _app()
    with TestClient(app) as client:
        for i in range(50):
            client.get(f"/no-such-route-{i}")

    labels = _label_values(metrics.registry)  # type: ignore[attr-defined]
    assert labels == {UNMATCHED_PATH}, (
        f"50 distinct unrouted paths produced {len(labels)} label values — the counter is "
        f"unbounded and an unauthenticated caller can exhaust process memory"
    )


def test_matched_routes_are_labeled_by_template_not_by_path_params() -> None:
    """Distinct path PARAMETERS must not multiply the label set either — `/things/{thing_id}` is
    one series however many ids are requested."""
    app, metrics = _app()
    with TestClient(app) as client:
        for i in range(25):
            client.get(f"/things/{i}")

    assert _label_values(metrics.registry) == {"/things/{thing_id}"}  # type: ignore[attr-defined]
