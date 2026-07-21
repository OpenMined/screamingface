from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import httpx
import pytest

import screamingface as sf
from screamingface import _profile


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [
            {
                "id": "codex",
                "display_name": "OpenAI Codex",
                "auth_methods": ["oauth"],
            },
            {
                "id": "gemini",
                "display_name": "Google Gemini",
                "auth_methods": ["oauth", "api_key"],
            },
        ],
        "models": [
            {
                "id": "codex/gpt-5.5",
                "provider": "codex",
                "supported_tools": ["web_search"],
            },
            {"id": "gemini/2.5-flash", "provider": "gemini", "supported_tools": []},
        ],
        "benchmarks": [
            {
                "id": "gpqa@1",
                "title": "GPQA Diamond",
                "cases_route": "/benchmarks/gpqa/1/cases",
                "grader": {"kind": "exact_choice", "route": "/graders/exact-choice/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": [],
                "max_tool_rounds": None,
            }
        ],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote/1"}],
    }


def _duplicate_record(value: dict[str, object], field: str) -> None:
    records = cast(list[object], value[field])
    records.append(records[0])


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
        host, port = cast(tuple[str, int], server.server_address)
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_engine_registry_drives_model_and_benchmark_discovery() -> None:
    routes = {"/.well-known/screamingface": json.dumps(_registry())}
    with _profile_server(routes) as engine:
        sf.config(engine=engine)

        assert sf.models.list() == ["codex/gpt-5.5", "gemini/2.5-flash"]
        assert sf.models.list(query="GEMINI", limit=1) == ["gemini/2.5-flash"]
        assert sf.models.list(tools=["web_search"]) == ["codex/gpt-5.5"]
        assert sf.benchmarks.list() == ["gpqa@1"]
        assert sf.benchmarks.list(query="GPQA") == ["gpqa@1"]
        assert sf.benchmarks.list(tools=["web_search"]) == []


def test_sdk_discovers_url4_safe_huggingface_aliases_from_engine_registry() -> None:
    registry = _registry()
    providers = cast(list[object], registry["providers"])
    providers.append(
        {
            "id": "huggingface",
            "display_name": "Hugging Face",
            "auth_methods": ["api_key"],
        }
    )
    models = cast(list[object], registry["models"])
    models.append(
        {
            "id": "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
            "provider": "huggingface",
            "supported_tools": [],
        }
    )

    with _profile_server({"/.well-known/screamingface": json.dumps(registry)}) as engine:
        sf.config(engine=engine)

        assert sf.models.list(query="huggingface/") == [
            "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra"
        ]


def test_benchmark_load_returns_the_engine_manifest() -> None:
    routes = {"/.well-known/screamingface": json.dumps(_registry())}
    with _profile_server(routes) as engine:
        sf.config(engine=engine)

        benchmark = sf.benchmarks.load("gpqa@1")

        assert benchmark.id == "gpqa@1"
        assert benchmark.title == "GPQA Diamond"
        with pytest.raises(sf.UnknownBenchmarkError, match="missing@1"):
            sf.benchmarks.load("missing@1")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.pop("models"), "missing field.*models"),
        (lambda value: value.pop("providers"), "missing field.*providers"),
        (lambda value: value.pop("benchmarks"), "missing field.*benchmarks"),
        (lambda value: value.update(extra=True), "unknown field.*extra"),
        (lambda value: value.update(schema="wrong"), "expected schema"),
        (lambda value: value.update(models={}), "models must be a list"),
        (lambda value: value.update(reducers={}), "reducers must be a list"),
        (lambda value: value.update(response_schemas=[]), "missing response schema"),
        (
            lambda value: value.update(response_schemas=["screamingface.recipe-result.v1"]),
            "missing response schema.*screamingface.report.v1",
        ),
        (
            lambda value: cast(list[dict[str, object]], value["models"])[0].update(
                provider="missing"
            ),
            "references unknown provider",
        ),
        (lambda value: value.pop("limits"), "missing field.*limits"),
        (
            lambda value: value.update(limits={"max_request_target_bytes": 0}),
            "max_request_target_bytes must be a positive integer",
        ),
        (
            lambda value: value.update(limits={"max_request_target_bytes": 61440, "extra": True}),
            "engine limits has unknown field.*extra",
        ),
        (
            lambda value: _duplicate_record(value, "models"),
            "duplicate model ID",
        ),
        (
            lambda value: _duplicate_record(value, "providers"),
            "duplicate provider ID",
        ),
        (
            lambda value: _duplicate_record(value, "reducers"),
            "duplicate reducer ID",
        ),
        (
            lambda value: _duplicate_record(value, "benchmarks"),
            "duplicate benchmark ID",
        ),
    ],
)
def test_registry_document_is_strict(monkeypatch, mutate, message: str) -> None:
    payload = _registry()
    mutate(payload)
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(payload))

    with pytest.raises(sf.EngineProfileError, match=message):
        _profile.load_registry()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"id": "model"}, "missing field"),
        (
            {"id": "model", "provider": "provider", "supported_tools": ["x", "x"]},
            "must not contain duplicates",
        ),
        (
            {"id": "model", "provider": "provider", "supported_tools": ["Web-Search"]},
            "lowercase",
        ),
        ({"id": "", "provider": "provider", "supported_tools": []}, "model ID"),
    ],
)
def test_model_records_are_strict(payload: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _profile._model_record(payload)


@pytest.mark.parametrize("route", ["relative", "//host/path", "/path?q=x", "/path#x"])
def test_reducer_routes_are_same_engine_paths(route: str) -> None:
    with pytest.raises(ValueError, match="same-engine absolute path"):
        _profile._reducer_record({"id": "reducer", "route": route})


def test_registry_transport_and_json_failures_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _profile.httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    with pytest.raises(sf.EngineConnectionError, match="could not reach"):
        _profile.load_registry()

    monkeypatch.setattr(
        _profile,
        "_get_text",
        lambda _path: '{"schema":"one","schema":"two"}',
    )
    with pytest.raises(sf.EngineProfileError, match="duplicate JSON field"):
        _profile.load_registry()


def test_registry_http_status_failures_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _profile.httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(503),
    )
    with pytest.raises(sf.EngineProtocolError, match="HTTP 503"):
        _profile._get_text(_profile.REGISTRY_PATH)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"id": "provider", "display_name": "Provider", "auth_methods": ["token"]},
            "unsupported provider auth method",
        ),
        (
            {"id": "provider", "display_name": "Provider", "auth_methods": []},
            "must not be empty",
        ),
    ],
)
def test_provider_records_are_strict(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _profile._provider_record(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "id": "research@1",
                "title": "Research",
                "cases_route": "/benchmarks/research/1/cases",
                "grader": {"kind": "rubric", "route": "/graders/rubric/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": ["web_search"],
                "max_tool_rounds": None,
            },
            "tool-enabled benchmark max_tool_rounds",
        ),
        (
            {
                "id": "gpqa@1",
                "title": "GPQA",
                "cases_route": "/benchmarks/gpqa/1/cases",
                "grader": {"kind": "exact_choice", "route": "/graders/exact-choice/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": [],
                "max_tool_rounds": 1,
            },
            "tool-free benchmark max_tool_rounds",
        ),
        (
            {
                "id": "gpqa@1",
                "title": "GPQA",
                "cases_route": "/benchmarks/gpqa/1/cases",
                "grader": "exact_choice",
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": [],
                "max_tool_rounds": None,
            },
            "benchmark grader must be an object",
        ),
    ],
)
def test_benchmark_records_are_strict(payload: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _profile._benchmark_record(payload)


def test_registry_collection_shapes_are_strict() -> None:
    with pytest.raises(TypeError, match="engine limits must be an object"):
        _profile._limits([])
    with pytest.raises(TypeError, match="must be a list"):
        _profile._string_list({}, "values")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.benchmarks.list(query=""), "query"),
        (lambda: sf.benchmarks.list(tools="web_search"), "tools"),
        (lambda: sf.models.list(tools=["Web-Search"]), "lowercase"),
        (lambda: sf.benchmarks.list(limit=0), "limit"),
        (lambda: sf.benchmarks.load(""), "benchmark ID"),
    ],
)
def test_benchmark_catalog_arguments_are_strict(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("grader", _profile.StrategyRecord("rubric", "/graders/rubric/1"), "grader"),
        (
            "aggregator",
            _profile.StrategyRecord("median", "/aggregators/median/1"),
            "aggregator",
        ),
        ("tools", ("code_execution",), "tool"),
    ],
)
def test_benchmark_manifest_support_is_explicit(field: str, value: object, message: str) -> None:
    record = _profile.BenchmarkRecord(
        "gpqa@1",
        "GPQA Diamond",
        "/benchmarks/gpqa/1/cases",
        _profile.StrategyRecord("exact_choice", "/graders/exact-choice/1"),
        _profile.StrategyRecord("mean", "/aggregators/mean/1"),
        (),
        None,
    )
    values = {
        "id": record.id,
        "title": record.title,
        "cases_route": record.cases_route,
        "grader": record.grader,
        "aggregator": record.aggregator,
        "tools": record.tools,
        "max_tool_rounds": record.max_tool_rounds,
    }
    values[field] = value
    changed = _profile.BenchmarkRecord(**values)

    with pytest.raises(ValueError, match=message):
        sf.benchmarks._benchmark(changed)
