"""Method selection — one benchmark, protocol variants chosen by keyword.

FEATURE: ifeval's corrective default vs the paper-comparable single_pass method.
STORY: as a researcher, my method choice is explicit — the wrong-comparison trap
(corrective vs published single-pass numbers) requires typing the choice out.
"""

from __future__ import annotations

import httpx
import pytest

import screamingface as sf

_PLAIN_PREFIX = "/benchmarks/ifeval/plain-revision"
_CHAIN_PREFIX = "/benchmarks/ifeval/chain-revision"


def _resource(method: str) -> dict[str, object]:
    prefix = _CHAIN_PREFIX if method == "corrective" else _PLAIN_PREFIX
    url4 = (
        f"(rows:0.0:{prefix}/cases*(checked:1.0:(record:0.0:{prefix}/check"
        "(/candidate($item.input)!'$candidate')!'$item.id')!'$record')!'case'"
        f";iteration.slice=0:1)!'$rows'"
    )
    return {
        "schema": "screamingface.benchmark.v1",
        "id": "ifeval",
        "revision": prefix.rsplit("/", 1)[-1],
        "case_count": 1,
        "total_case_count": 541,
        "required_models": [],
        "url4": url4,
        "method": method,
        "methods": ["corrective", "single_pass"],
        "default_method": "corrective",
    }


class _Engine:
    def __init__(self) -> None:
        self.benchmark_queries: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = self._payload(request)
        if payload is None:
            return httpx.Response(404)
        return httpx.Response(200, json=payload)

    def _payload(self, request: httpx.Request) -> dict[str, object] | None:
        payloads: dict[str, dict[str, object]] = {
            "/v1/models": {
                "object": "list",
                "data": [{"id": "provider/m", "owned_by": "provider"}],
            },
            "/v1/benchmarks": {
                "object": "list",
                "default": "ifeval",
                "data": [
                    {
                        "object": "benchmark",
                        "id": "ifeval",
                        "title": "IFEval",
                        "description": "two methods",
                        "href": "/v1/benchmarks/ifeval",
                        "methods": ["corrective", "single_pass"],
                        "default_method": "corrective",
                    }
                ],
            },
        }
        if request.url.path in payloads:
            return payloads[request.url.path]
        if request.url.path == "/v1/benchmarks/ifeval":
            params = dict(request.url.params)
            self.benchmark_queries.append(params)
            method = params.get("method", "corrective")
            if method in ("corrective", "single_pass"):
                return _resource(method)
        return None


def _client(engine: _Engine) -> sf.Client:
    return sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
    )


def test_omitted_method_sends_no_method_parameter() -> None:
    # INVARIANT: the DEFAULT is the engine's decision, not the SDK's — omitting the
    # keyword must omit the query parameter so the manifest stays the single authority.
    engine = _Engine()
    with _client(engine) as client:
        benchmark = client.benchmarks.get("ifeval")

    assert engine.benchmark_queries[-1].get("method") is None
    assert benchmark.revision == "chain-revision"


def test_get_with_method_fetches_that_variant() -> None:
    engine = _Engine()
    with _client(engine) as client:
        benchmark = client.benchmarks.get("ifeval", method="single_pass")

    assert engine.benchmark_queries[-1]["method"] == "single_pass"
    assert benchmark.revision == "plain-revision"


def test_evaluate_threads_method_into_the_resource_fetch() -> None:
    engine = _Engine()
    with _client(engine) as client:
        with pytest.raises(sf.PlanningError):
            # The fetch succeeds (recorded below); planning then fails on the absent
            # model catalog match — enough to prove the method reached the wire.
            client.evaluate(
                sf.Model("provider/absent"),
                benchmark="ifeval",
                limit=1,
                method="single_pass",
            )

    assert any(query.get("method") == "single_pass" for query in engine.benchmark_queries)


def test_evaluate_rejects_a_blank_method() -> None:
    engine = _Engine()
    with _client(engine) as client:
        with pytest.raises(ValueError):
            client.evaluate(sf.Model("provider/m"), benchmark="ifeval", limit=1, method="  ")
