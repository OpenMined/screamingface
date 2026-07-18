from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import screamingface as sf


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": ["screamingface.fusion-result.v1"],
        "models": [
            {"id": "codex/gpt-5.5", "supported_tools": ["web_search"]},
            {"id": "gemini/2.5", "supported_tools": []},
            {"id": "gemini/3.1-pro-preview", "supported_tools": []},
        ],
        "reducers": [{"id": "majority_vote", "route": "/sf/reducers/majority-vote"}],
        "benchmarks": [
            {
                "id": "gpqa@1",
                "manifest": "/sf/benchmarks/gpqa@1",
                "tools": [],
            },
            {
                "id": "draco@1",
                "manifest": "/sf/benchmarks/draco@1",
                "tools": ["web_search"],
            },
        ],
    }


def _gpqa_manifest() -> dict[str, object]:
    return {
        "schema": "screamingface.benchmark.v1",
        "id": "gpqa@1",
        "title": "GPQA Diamond",
        "tools": [],
        "cases": {
            "url": "/sf/benchmarks/gpqa@1/cases",
            "format": "ndjson",
        },
        "grader": {"type": "exact_choice"},
        "aggregator": {"type": "mean"},
    }


def _draco_manifest() -> dict[str, object]:
    return {
        "schema": "screamingface.benchmark.v1",
        "id": "draco@1",
        "title": "DRACO",
        "tools": ["web_search"],
        "cases": {
            "url": "/sf/benchmarks/draco@1/cases",
            "format": "ndjson",
        },
        "grader": {
            "type": "rubric",
            "model": "gemini/3.1-pro-preview",
            "prompt": "Pinned judge prompt",
            "passes": 5,
            "params": {
                "temperature": 0.2,
                "reasoning": "low",
                "max_tokens": 4096,
            },
        },
        "aggregator": {"type": "mean"},
    }


def _routes() -> dict[str, str]:
    return {
        "/.well-known/screamingface": json.dumps(_registry()),
        "/sf/benchmarks/gpqa@1": json.dumps(_gpqa_manifest()),
        "/sf/benchmarks/gpqa@1/cases": (
            '{"id":"q1","input":"2 + 2?\\n\\nA. 3\\nB. 4","reference":"B",'
            '"metadata":{"subject":"math"}}\n'
        ),
        "/sf/benchmarks/draco@1": json.dumps(_draco_manifest()),
        "/sf/benchmarks/draco@1/cases": (
            '{"id":"d1","input":"Research this",'
            '"reference":{"sections":[{"id":"facts","criteria":[]}]},'
            '"metadata":{"domain":"science"}}\n'
        ),
    }


@contextmanager
def _profile_server(routes: Mapping[str, str]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            encoded = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address = server.server_address
        host, port = str(address[0]), int(address[1])
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_discovery_returns_filtered_canonical_ids() -> None:
    with _profile_server(_routes()) as engine:
        sf.config(engine=engine)

        assert sf.models.list() == [
            "codex/gpt-5.5",
            "gemini/2.5",
            "gemini/3.1-pro-preview",
        ]
        assert sf.models.list(query="GEMINI", limit=1) == ["gemini/2.5"]
        assert sf.models.list(tools=["web_search"]) == ["codex/gpt-5.5"]
        assert sf.benchmarks.list() == ["gpqa@1", "draco@1"]
        assert sf.benchmarks.list(query="DRACO", tools=["web_search"]) == ["draco@1"]


def test_load_eagerly_validates_manifest_and_cases() -> None:
    with _profile_server(_routes()) as engine:
        sf.config(engine=engine)
        gpqa = sf.benchmarks.load("gpqa@1")
        draco = sf.benchmarks.load("draco@1")

    assert gpqa.id == "gpqa@1"
    assert gpqa.title == "GPQA Diamond"
    assert isinstance(gpqa.grader, sf.graders.ExactChoice)
    assert gpqa._materialize_cases() == (
        sf.Case(
            "q1",
            "2 + 2?\n\nA. 3\nB. 4",
            reference="B",
            metadata={"subject": "math"},
        ),
    )
    assert draco.tools == ("web_search",)
    assert isinstance(draco.grader, sf.graders.Rubric)
    assert draco.grader.passes == 5


def test_unknown_benchmark_fails_before_manifest_request() -> None:
    with _profile_server(_routes()) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.UnknownBenchmarkError, match="missing@1"):
            sf.benchmarks.load("missing@1")


def test_duplicate_case_ids_are_invalid() -> None:
    routes = _routes()
    routes["/sf/benchmarks/gpqa@1/cases"] *= 2
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.InvalidBenchmarkError, match="duplicate case ID"):
            sf.benchmarks.load("gpqa@1")


def test_malformed_registry_is_an_engine_profile_error() -> None:
    with _profile_server({"/.well-known/screamingface": "not json"}) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.EngineProfileError, match="registry"):
            sf.models.list()


def test_unreachable_engine_is_a_connection_error() -> None:
    sf.config(engine="http://127.0.0.1:1")
    with pytest.raises(sf.EngineConnectionError, match="127.0.0.1:1"):
        sf.models.list()


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: sf.models.list(query=""), "query"),
        (lambda: sf.models.list(tools="web_search"), "sequence"),
        (lambda: sf.models.list(tools=[""]), "non-empty"),
        (lambda: sf.models.list(limit=0), "positive"),
        (lambda: sf.benchmarks.load(""), "benchmark ID"),
    ],
)
def test_registry_argument_validation(call, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        call()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(schema="wrong"), "expected schema"),
        (lambda value: value.update(response_schemas=[]), "missing response schema"),
        (lambda value: value.update(models="wrong"), "list of objects"),
        (
            lambda value: value["models"].append(value["models"][0]),
            "duplicate model ID",
        ),
        (
            lambda value: value["reducers"][0].update(route="https://other.test/x"),
            "same-engine",
        ),
        (
            lambda value: value["benchmarks"][0].update(extra=True),
            "unknown field",
        ),
    ],
)
def test_registry_schema_is_strict(mutate, message: str) -> None:
    registry = _registry()
    mutate(registry)
    routes = {"/.well-known/screamingface": json.dumps(registry)}
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.EngineProfileError, match=message):
            sf.models.list()


@pytest.mark.parametrize(
    ("mutate", "message", "error"),
    [
        (lambda value: value.update(schema="wrong"), "expected schema", sf.InvalidBenchmarkError),
        (lambda value: value.update(id="other@1"), "does not match", sf.InvalidBenchmarkError),
        (
            lambda value: value.update(tools=["web_search"]),
            "tools do not match",
            sf.InvalidBenchmarkError,
        ),
        (lambda value: value["cases"].update(format="json"), "ndjson", sf.InvalidBenchmarkError),
        (
            lambda value: value.update(grader={"type": "other"}),
            "grader type",
            sf.InvalidBenchmarkError,
        ),
        (
            lambda value: value.update(aggregator={"type": "median"}),
            "aggregator",
            sf.InvalidBenchmarkError,
        ),
    ],
)
def test_benchmark_manifest_is_strict(mutate, message: str, error: type[Exception]) -> None:
    manifest = _gpqa_manifest()
    mutate(manifest)
    routes = _routes()
    routes["/sf/benchmarks/gpqa@1"] = json.dumps(manifest)
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(error, match=message):
            sf.benchmarks.load("gpqa@1")


def test_rubric_manifest_requires_an_advertised_judge_model() -> None:
    manifest = _draco_manifest()
    grader = manifest["grader"]
    assert isinstance(grader, dict)
    grader["model"] = "missing/judge"
    routes = _routes()
    routes["/sf/benchmarks/draco@1"] = json.dumps(manifest)
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.UnknownModelError, match="missing/judge"):
            sf.benchmarks.load("draco@1")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("", "no cases"),
        ('{"id":"q","input":"x","reference":null,"metadata":{}}\n', "no reference"),
        ('{"id":"q","input":"x","reference":"A"}\n', "missing field"),
        ("not json\n", "not JSON"),
    ],
)
def test_case_stream_is_strict(body: str, message: str) -> None:
    routes = _routes()
    routes["/sf/benchmarks/gpqa@1/cases"] = body
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.InvalidBenchmarkError, match=message):
            sf.benchmarks.load("gpqa@1")


def test_profile_http_failure_is_protocol_error() -> None:
    registry = _registry()
    benchmarks = registry["benchmarks"]
    assert isinstance(benchmarks, list)
    first = benchmarks[0]
    assert isinstance(first, dict)
    first["manifest"] = "/missing"
    routes = {"/.well-known/screamingface": json.dumps(registry)}
    with _profile_server(routes) as engine:
        sf.config(engine=engine)
        with pytest.raises(sf.EngineProtocolError, match="HTTP 404"):
            sf.benchmarks.load("gpqa@1")
