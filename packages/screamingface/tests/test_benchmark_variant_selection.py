"""Protocol variants are ordinary Engine-owned Benchmark identities."""

from __future__ import annotations

import httpx

import screamingface as sf


class _Engine:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "default": "ifeval",
                    "data": [
                        {
                            "object": "benchmark",
                            "id": benchmark_id,
                            "family": "ifeval",
                            "variant": variant,
                            "title": title,
                            "description": title,
                            "href": f"/v1/benchmarks/{benchmark_id}",
                        }
                        for benchmark_id, variant, title in (
                            ("ifeval", "canonical", "IFEval"),
                            ("ifeval-corrective", "corrective", "IFEval Corrective"),
                            (
                                "ifeval-corrective-ensemble",
                                "corrective-ensemble",
                                "IFEval Corrective Ensemble",
                            ),
                        )
                    ],
                },
            )
        if request.url.path.startswith("/v1/benchmarks/"):
            benchmark_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "schema": "screamingface.benchmark.v1",
                    "id": benchmark_id,
                    "family": "ifeval",
                    "variant": "corrective" if benchmark_id.endswith("corrective") else "canonical",
                    "revision": f"{benchmark_id}-revision",
                    "case_count": 1,
                    "total_case_count": 541,
                    "required_models": [],
                    "url4": "(/candidate('question')!'$candidate')!'answer'",
                },
            )
        return httpx.Response(404)


def test_each_variant_is_fetched_as_one_explicit_benchmark_identity() -> None:
    engine = _Engine()
    with sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine),
    ) as client:
        canonical = client.benchmarks.get("ifeval")
        corrective = client.benchmarks.get("ifeval-corrective")
        ensemble = client.benchmarks.get("ifeval-corrective-ensemble")

    assert canonical.family == corrective.family == ensemble.family == "ifeval"
    assert canonical.variant == "canonical"
    assert corrective.variant == "corrective"
    assert ensemble.variant == "corrective-ensemble"
    assert "/v1/benchmarks/ifeval?limit=1" not in engine.paths
    assert "/v1/benchmarks/ifeval" in engine.paths
    assert "/v1/benchmarks/ifeval-corrective" in engine.paths
    assert "/v1/benchmarks/ifeval-corrective-ensemble" in engine.paths
