# ruff: noqa: E501
"""Generated OpenAPI contract and branded reference UI for ScreamingFace engine."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from typing import Any

from screamingface_engine.aggregators import MEAN_ROUTE, REPORT_SCHEMA
from screamingface_engine.benchmarks import DRACO_TOOL_POLICY_ROUTE, GPQA_CASES_ROUTE
from screamingface_engine.catalog import (
    BENCHMARK_ROUTES,
    PUBLIC_PROVIDERS,
    ModelRoute,
    registry_document,
)
from screamingface_engine.graders import CASE_GRADE_SCHEMA, EXACT_CHOICE_ROUTE
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]

OPENAPI_PATH = "/openapi.json"
DOCS_PATH = "/docs"
ENGINE_VERSION = "0.1.0"


class DocumentationASGI:
    """Serve one OpenAPI snapshot generated from the engine's executable route snapshot."""

    def __init__(self, *, max_request_target_bytes: int) -> None:
        self._max_request_target_bytes = max_request_target_bytes
        self._document: dict[str, Any] | None = None
        self._document_body: bytes | None = None

    @staticmethod
    def handles(scope: Mapping[str, Any]) -> bool:
        return str(scope.get("path", "")) in {DOCS_PATH, f"{DOCS_PATH}/", OPENAPI_PATH}

    def configure(self, model_routes: Sequence[ModelRoute]) -> None:
        document = openapi_document(
            model_routes,
            max_request_target_bytes=self._max_request_target_bytes,
        )
        self._document = document
        self._document_body = json.dumps(
            document,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()

    async def __call__(self, scope: Mapping[str, Any], _receive: Receive, send: Send) -> None:
        method = str(scope.get("method", "GET")).upper()
        if method != "GET":
            await _send_json_error(
                send,
                405,
                "method_not_allowed",
                "Documentation routes are GET-only.",
            )
            return
        if self._document is None or self._document_body is None:
            await _send_json_error(send, 503, "not_ready", "Engine documentation is not ready.")
            return
        path = str(scope.get("path", ""))
        if path == OPENAPI_PATH:
            await _send_response(send, 200, self._document_body, b"application/json")
            return
        await _send_response(
            send,
            200,
            _DOCS_HTML.encode(),
            b"text/html; charset=utf-8",
        )


def openapi_document(
    model_routes: Sequence[ModelRoute],
    *,
    max_request_target_bytes: int,
) -> dict[str, Any]:
    """Build the complete current HTTP contract from one executable model snapshot."""

    routes = tuple(model_routes)
    if not routes:
        raise ValueError("OpenAPI requires at least one model route")
    registry = registry_document(routes, max_request_target_bytes=max_request_target_bytes)
    paths: dict[str, Any] = {
        "/healthz": _health_path(),
        "/.well-known/screamingface": _registry_path(),
        OPENAPI_PATH: _openapi_path(),
        DOCS_PATH: _docs_path(),
        "/v1": _evaluation_path(max_request_target_bytes),
        "/v1/connections": _connections_path(),
        "/v1/connections/{provider}": _connection_path(),
        "/v1/connections/{provider}/oauth": _oauth_path(),
        "/v1/connections/{provider}/api-key": _api_key_path(),
        "/auth/callback": _callback_path("OpenAI Codex"),
        "/oauth2callback": _callback_path("Google Gemini", advertised=False),
        "/callback": _callback_path("Anthropic"),
        GPQA_CASES_ROUTE: _cases_path(),
        DRACO_TOOL_POLICY_ROUTE: _tool_policy_path(),
        MAJORITY_VOTE_ROUTE: _majority_vote_path(),
        EXACT_CHOICE_ROUTE: _exact_choice_path(),
        MEAN_ROUTE: _mean_path(),
    }
    for route in routes:
        paths[route.route] = _model_path(route)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "ScreamingFace engine",
            "version": ENGINE_VERSION,
            "summary": "URL4 execution, model routing, benchmark primitives, and connections.",
            "description": (
                "The current local-first ScreamingFace engine contract. The Python SDK sends "
                "complete URL4 expressions only to this engine. The engine owns model and tool "
                "routing; the SDK never calls AI Gateway directly. Dynamic model paths in this "
                "document come from the same AI Gateway catalog snapshot used to register the "
                "running URL4 node."
            ),
        },
        "servers": [{"url": "/", "description": "This ScreamingFace engine instance"}],
        "tags": [
            {"name": "System", "description": "Health and machine-readable contracts."},
            {"name": "Evaluation", "description": "Complete URL4 expression execution."},
            {
                "name": "Connections",
                "description": "Local provider and Tavily credential control.",
            },
            {
                "name": "OAuth callbacks",
                "description": "Browser return routes; applications do not call these directly.",
            },
            {
                "name": "URL4 models",
                "description": "Dynamic model leaves used inside complete expressions.",
            },
            {
                "name": "URL4 benchmark data",
                "description": "Versioned case collections resolved by the engine.",
            },
            {
                "name": "URL4 reducers",
                "description": "Deterministic answer reduction primitives.",
            },
            {
                "name": "URL4 graders",
                "description": "Per-case grading primitives.",
            },
            {
                "name": "URL4 aggregators",
                "description": "Cross-case report aggregation primitives.",
            },
        ],
        "paths": paths,
        "components": {"schemas": _schemas()},
        "x-screamingface-architecture": {
            "primary_transport": "GET /v1?q=…",
            "sdk_calls_ai_gateway": False,
            "request_flow": [
                "ScreamingFace Python SDK",
                "ScreamingFace engine / URL4 node",
                "AI Gateway for model inference",
                "model provider",
            ],
            "tool_flow": [
                "ScreamingFace engine selects the route's tool backend",
                "OpenRouter server tools or a bounded Tavily agent loop",
            ],
            "model_catalog": (
                "Fetched once from AI Gateway during engine startup; the node and this document "
                "use the same validated snapshot."
            ),
            "response_boundary": (
                "URL4 execution returns text/plain by default. The SDK requests "
                "text/event-stream for lifecycle visibility; its terminal complete event "
                "contains that same plaintext value. JSON-shaped values are parsed by the SDK."
            ),
        },
        "x-screamingface-status": {
            "contract": "current executable engine",
            "gpqa": {"executable": True, "benchmark_id": "gpqa@1"},
            "draco": {
                "executable": False,
                "benchmark_id": "draco@1",
                "blocking_capability": (
                    "Register and verify the production DRACO cases, grader protocol, model "
                    "routes, and candidate configuration. The versioned web-tool policy route "
                    "already exists. Each candidate already "
                    "fits one complete URL4 benchmark transaction."
                ),
            },
            "hosted_deployment": (
                "Not represented here. The current engine is local-first; connection control "
                "has no public multi-user identity boundary."
            ),
        },
        "x-screamingface-url4": {
            "registry": registry,
            "limits": registry["limits"],
            "response_schemas": registry["response_schemas"],
            "expression_transport": {
                "method": "GET",
                "path": "/v1",
                "query_parameter": "q",
                "response_content_types": ["text/plain", "text/event-stream"],
            },
            "route_semantics": (
                "Model, data, reducer, grader, and aggregator paths are URL4 node routes. "
                "The SDK normally composes them into one expression sent through /v1."
            ),
            "tools": {
                "ids": ["web_search", "web_fetch"],
                "owner": "ScreamingFace engine",
                "backend_selection": {
                    "openrouter": "OpenRouter-managed server tools",
                    "huggingface": "engine-managed Tavily agent loop",
                },
                "limits": {"max_tool_calls_per_turn": 8, "max_total_tool_calls": 32},
                "policy": _tool_policy_reference(),
                "official_benchmarks": (
                    "The manifest names one immutable same-engine tool-policy data route. The "
                    "SDK resolves it once in each case graph and passes the value beside the "
                    "question in screamingface.model-input.v1. Model routes select the private "
                    "OpenRouter or Tavily backend."
                ),
                "custom_benchmarks": (
                    "Portable custom benchmarks serialize the same policy inline as generic "
                    "tools, tools.max_calls, and web_search.* URL4 parameters."
                ),
            },
            "benchmarks": [benchmark.public for benchmark in BENCHMARK_ROUTES],
        },
    }


def _health_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "health",
            "System",
            "Check process health",
            "Returns `ok` after the engine and its startup model catalog are ready.",
            {"200": _text_response("Healthy engine", "ok")},
        )
    }


def _registry_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "get_engine_registry",
            "System",
            "Discover executable engine capabilities",
            (
                "Returns `screamingface.registry.v1` as serialized JSON in a text/plain body. "
                "Models are the routes actually registered from the startup Gateway snapshot."
            ),
            {
                "200": _text_response(
                    "Current capability registry",
                    '{"schema":"screamingface.registry.v1","models":[]}',
                    schema={"$ref": "#/components/schemas/Registry"},
                )
            },
        )
    }


def _openapi_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "get_openapi_document",
            "System",
            "Read the generated OpenAPI document",
            "Generated from the same executable model-route snapshot as the running node.",
            {"200": _json_response("OpenAPI 3.1 document", {"type": "object"})},
        )
    }


def _docs_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "get_api_reference",
            "System",
            "Open the interactive API reference",
            "A read-only, locally served rendering of `/openapi.json`.",
            {"200": _html_response("ScreamingFace engine API reference")},
        )
    }


def _evaluation_path(max_request_target_bytes: int) -> dict[str, Any]:
    return {
        "get": _operation(
            "evaluate_url4",
            "Evaluation",
            "Evaluate one complete URL4 expression",
            (
                "Primary SDK transport. The expression can resolve model calls, data collections, "
                "reduction, grading, iteration, slicing, error collection, and aggregation. The "
                f"encoded request target is limited to {max_request_target_bytes} bytes. Send "
                "`Accept: text/event-stream` for typed accepted/running/terminal events; omit it "
                "for the unchanged final plaintext value."
            ),
            {
                "200": {
                    "description": "Resolved URL4 value or evaluation event stream",
                    "content": {
                        "text/plain": {
                            "schema": {"type": "string"},
                            "example": (
                                '{"schema":"screamingface.report.v1","benchmark_id":"gpqa@1"}'
                            ),
                        },
                        "text/event-stream": {
                            "schema": {"type": "string"},
                            "x-screamingface-event-schema": {
                                "$ref": "#/components/schemas/EvaluationEvent"
                            },
                            "example": (
                                "event: accepted\n"
                                'data: {"schema":"screamingface.evaluation-event.v1",'
                                '"type":"accepted"}\n\n'
                            ),
                        },
                    },
                },
                "400": _engine_error_response("Malformed or invalid URL4 expression"),
                "401": _engine_error_response("Required provider or tool connection is absent"),
                "402": _engine_error_response("Provider payment is required"),
                "414": _engine_error_response("Encoded request target is too large"),
                "422": _engine_error_response("Bounded tool budget was exhausted"),
                "429": _engine_error_response("Provider rate limit"),
                "502": _engine_error_response("Provider or tool service unavailable"),
                "503": _engine_error_response("Engine not ready or at capacity"),
                "504": _engine_error_response("Evaluation timeout"),
            },
            parameters=[
                {
                    "name": "Accept",
                    "in": "header",
                    "required": False,
                    "description": (
                        "Use `text/event-stream` to receive lifecycle events and the final "
                        "plaintext value in the terminal `complete` event."
                    ),
                    "schema": {
                        "type": "string",
                        "enum": ["text/plain", "text/event-stream"],
                    },
                },
                _query_parameter(
                    "q",
                    "Complete, percent-encoded URL4 expression.",
                    required=True,
                    example="('cats','dogs')!'Compare'",
                ),
            ],
        )
    }


def _connections_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "list_connections",
            "Connections",
            "List provider and tool connection states",
            (
                "Returns the local engine's public connection projection. Secrets are never "
                "returned. Model-provider state is projected from AI Gateway; Tavily state is "
                "owned by this engine process."
            ),
            {
                "200": _json_response(
                    "Connection states",
                    {"$ref": "#/components/schemas/ConnectionList"},
                ),
                "502": _connection_error_response("AI Gateway unavailable"),
            },
        )
    }


def _connection_path() -> dict[str, Any]:
    provider = _provider_parameter()
    return {
        "parameters": [provider],
        "get": _operation(
            "get_connection",
            "Connections",
            "Read one connection state",
            "Returns status without exposing a credential.",
            {
                "200": _json_response(
                    "Connection state",
                    {"$ref": "#/components/schemas/Connection"},
                ),
                "404": _connection_error_response("Unknown provider"),
            },
        ),
        "delete": _operation(
            "disconnect_provider",
            "Connections",
            "Disconnect one provider or tool",
            "Removes the engine-managed connection. Returns no body.",
            {
                "204": {"description": "Disconnected"},
                "404": _connection_error_response("Unknown provider"),
                "502": _connection_error_response("AI Gateway unavailable"),
            },
        ),
    }


def _oauth_path() -> dict[str, Any]:
    return {
        "parameters": [_provider_parameter()],
        "post": {
            **_operation(
                "start_provider_oauth",
                "Connections",
                "Start an OAuth connection",
                (
                    "Returns an authorization URL for providers that advertise OAuth. The request "
                    "body must be empty. Gemini currently advertises API-key auth only."
                ),
                {
                    "200": _json_response(
                        "Pending OAuth flow",
                        {"$ref": "#/components/schemas/OAuthStart"},
                    ),
                    "400": _connection_error_response("Auth method unsupported or body not empty"),
                    "404": _connection_error_response("Unknown provider"),
                    "502": _connection_error_response("AI Gateway unavailable"),
                },
            ),
            "requestBody": {
                "required": False,
                "description": "No request body is accepted.",
                "content": {},
            },
        },
    }


def _api_key_path() -> dict[str, Any]:
    return {
        "parameters": [_provider_parameter()],
        "put": {
            **_operation(
                "set_provider_api_key",
                "Connections",
                "Create or replace an API-key connection",
                (
                    "The secret is accepted only in the JSON request body. It is never returned, "
                    "placed in URL4, or logged on an argument vector. Tavily remains local process "
                    "state; model-provider credentials are delegated to AI Gateway storage."
                ),
                {
                    "200": _json_response(
                        "Connected provider",
                        {"$ref": "#/components/schemas/Connection"},
                    ),
                    "400": _connection_error_response("Invalid API key body"),
                    "404": _connection_error_response("Unknown provider"),
                    "413": _connection_error_response("Body exceeds 16 KiB"),
                    "415": _connection_error_response("Content-Type is not application/json"),
                    "502": _connection_error_response("AI Gateway unavailable"),
                },
            ),
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ApiKeyInput"},
                        "example": {"api_key": "••••••••"},
                    }
                },
            },
        },
    }


def _callback_path(provider: str, *, advertised: bool = True) -> dict[str, Any]:
    status = (
        "This callback belongs to an advertised OAuth method."
        if advertised
        else "Reserved adapter callback; this provider does not currently advertise OAuth."
    )
    return {
        "get": _operation(
            f"complete_{_identifier(provider)}_oauth",
            "OAuth callbacks",
            f"Complete {provider} OAuth",
            f"Browser-facing callback, not an SDK endpoint. {status}",
            {
                "200": _html_response("Authorization complete"),
                "400": _html_response("Invalid or expired callback"),
            },
            parameters=[
                _query_parameter("code", "Provider authorization code.", required=True),
                _query_parameter("state", "OAuth state value.", required=True),
            ],
        )
    }


def _model_path(route: ModelRoute) -> dict[str, Any]:
    capability = (
        f" Supports engine-owned tools: {', '.join(route.tool_capabilities)}."
        if route.tool_capabilities
        else " Does not advertise engine-owned tools."
    )
    return {
        "get": _operation(
            f"invoke_{_identifier(route.id)}",
            "URL4 models",
            f"Invoke {route.id}",
            (
                "URL4 intent-processor route. `q` is a URL4 request fragment whose context becomes "
                "the user message and whose intent becomes the system instruction. An official "
                "tool-enabled benchmark instead supplies a `screamingface.model-input.v1` context "
                "holding the question and its resolved versioned tool policy. The engine "
                f"forwards the decoded model request to AI Gateway.{capability}"
            ),
            {
                "200": _text_response("Model answer", "A"),
                "400": _engine_error_response("Invalid model or tool parameters"),
                "401": _engine_error_response("Provider or Tavily connection required"),
                "402": _engine_error_response("Provider payment required"),
                "422": _engine_error_response("Tool budget exhausted"),
                "429": _engine_error_response("Provider rate limited"),
                "502": _engine_error_response("Provider unavailable or invalid response"),
            },
            parameters=_model_parameters(route),
            extensions={
                "x-screamingface-url4-route": "model",
                "x-screamingface-model": {
                    "id": route.id,
                    "provider": route.provider,
                    "supported_tools": list(route.tool_capabilities),
                },
            },
        )
    }


def _model_parameters(route: ModelRoute) -> list[dict[str, Any]]:
    parameters = [
        _query_parameter(
            "q",
            "URL4 request fragment, for example `(question)!'Answer briefly'`.",
            required=True,
        ),
        _query_parameter("temperature", "Finite model temperature.", schema={"type": "number"}),
        _query_parameter(
            "max_tokens",
            "Positive maximum output-token count.",
            schema={"type": "integer", "minimum": 1},
        ),
        _query_parameter(
            "reasoning",
            "Reasoning effort forwarded to AI Gateway.",
            schema={"type": "string", "enum": ["low", "medium", "high"]},
        ),
    ]
    if route.tool_capabilities:
        parameters.extend(
            [
                _query_parameter(
                    "tools",
                    "Colon-separated capability IDs: `web_search:web_fetch`.",
                ),
                _query_parameter(
                    "tools.max_calls",
                    "Positive tool-call budget for this model answer.",
                    schema={"type": "integer", "minimum": 1},
                ),
                _query_parameter(
                    "web_search.*",
                    (
                        "Provider-neutral web-search policy parameters. See "
                        "`x-screamingface-url4.tools.policy` in `/openapi.json`."
                    ),
                    schema={"type": "string"},
                ),
            ]
        )
    return parameters


def _cases_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "read_gpqa_1_cases",
            "URL4 benchmark data",
            "Resolve pinned GPQA Diamond cases",
            (
                "Versioned NDJSON collection used inside benchmark URL4. The engine environment "
                "must provide `HF_TOKEN`; cases are fetched from Hugging Face and are not bundled."
            ),
            {
                "200": {
                    "description": "GPQA cases",
                    "content": {
                        "application/x-ndjson": {
                            "schema": {"type": "string"},
                            "example": '{"id":"…","input":"…","reference":"A"}\n',
                        }
                    },
                },
                "401": _engine_error_response("Dataset authentication required"),
                "502": _engine_error_response("Dataset unavailable"),
            },
            extensions={"x-screamingface-url4-route": "data"},
        )
    }


def _tool_policy_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "read_draco_1_tool_policy",
            "URL4 benchmark data",
            "Resolve the pinned DRACO web-tool policy",
            (
                "Immutable provider-neutral policy data used by the future draco@1 manifest. "
                "The route contains no credentials or backend names. DRACO itself remains "
                "unadvertised until its other production contracts are complete."
            ),
            {
                "200": _text_response(
                    "Serialized benchmark tool policy",
                    '{"schema":"screamingface.tool-policy.v1","tools":["web_search","web_fetch"]}',
                    schema={"$ref": "#/components/schemas/ToolPolicy"},
                )
            },
            extensions={"x-screamingface-url4-route": "data"},
        )
    }


def _majority_vote_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "reduce_majority_vote_1",
            "URL4 reducers",
            "Reduce member answers by majority vote",
            (
                "Expects a URL4 request whose resolved intent is a JSON object with contiguous "
                "`member_1` through `member_n` string answers, with n >= 2."
            ),
            {
                "200": _text_response("Selected answer", "A"),
                "400": _engine_error_response("Malformed reducer input"),
            },
            parameters=[_url4_fragment_parameter()],
            extensions={"x-screamingface-url4-route": "reducer"},
        )
    }


def _exact_choice_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "grade_exact_choice_1",
            "URL4 graders",
            "Grade a Recipe and its members against one exact choice",
            (
                "Expects `screamingface.recipe-result.v1` as resolved context and benchmark ID, "
                "case ID, and sealed reference as resolved intent."
            ),
            {
                "200": _text_response(
                    "Serialized case grade",
                    f'{{"schema":"{CASE_GRADE_SCHEMA}","benchmark_id":"gpqa@1"}}',
                    schema={"$ref": "#/components/schemas/CaseGrade"},
                ),
                "400": _engine_error_response("Malformed Recipe or case input"),
            },
            parameters=[_url4_fragment_parameter()],
            extensions={"x-screamingface-url4-route": "grader"},
        )
    }


def _mean_path() -> dict[str, Any]:
    return {
        "get": _operation(
            "aggregate_mean_1",
            "URL4 aggregators",
            "Aggregate exact-choice case grades",
            (
                "Expects a non-empty JSON array of case-grade rows as resolved intent. URL4 "
                "collection errors become typed report failures; scores use complete paired cases."
            ),
            {
                "200": _text_response(
                    "Serialized benchmark report",
                    f'{{"schema":"{REPORT_SCHEMA}","benchmark_id":"gpqa@1"}}',
                    schema={"$ref": "#/components/schemas/Report"},
                ),
                "400": _engine_error_response("Malformed grade rows"),
            },
            parameters=[_url4_fragment_parameter()],
            extensions={"x-screamingface-url4-route": "aggregator"},
        )
    }


def _operation(
    operation_id: str,
    tag: str,
    summary: str,
    description: str,
    responses: Mapping[str, Any],
    *,
    parameters: Sequence[Mapping[str, Any]] = (),
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": [tag],
        "summary": summary,
        "description": description,
        "responses": dict(responses),
    }
    if parameters:
        operation["parameters"] = [dict(parameter) for parameter in parameters]
    if extensions:
        operation.update(extensions)
    return operation


def _query_parameter(
    name: str,
    description: str,
    *,
    required: bool = False,
    schema: Mapping[str, Any] | None = None,
    example: object | None = None,
) -> dict[str, Any]:
    parameter: dict[str, Any] = {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": dict(schema or {"type": "string"}),
    }
    if example is not None:
        parameter["example"] = example
    return parameter


def _provider_parameter() -> dict[str, Any]:
    return {
        "name": "provider",
        "in": "path",
        "required": True,
        "description": "Advertised provider ID.",
        "schema": {
            "type": "string",
            "enum": [provider.id for provider in PUBLIC_PROVIDERS],
        },
    }


def _url4_fragment_parameter() -> dict[str, Any]:
    return _query_parameter(
        "q",
        "URL4 request fragment resolved into context, intent, and route parameters.",
        required=True,
    )


def _text_response(
    description: str,
    example: str,
    *,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    media: dict[str, Any] = {
        "schema": {"type": "string"},
        "example": example,
    }
    if schema is not None:
        # The URL4 wire contract is text/plain even when that text is serialized JSON.
        media["x-screamingface-serialized-schema"] = dict(schema)
    return {
        "description": description,
        "content": {"text/plain": media},
    }


def _json_response(description: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": dict(schema)}},
    }


def _html_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"text/html": {"schema": {"type": "string"}}},
    }


def _engine_error_response(description: str) -> dict[str, Any]:
    return _json_response(description, {"$ref": "#/components/schemas/EngineError"})


def _connection_error_response(description: str) -> dict[str, Any]:
    return _json_response(description, {"$ref": "#/components/schemas/ConnectionError"})


def _schemas() -> dict[str, Any]:
    nullable_string = {"type": ["string", "null"]}
    nullable_number = {"type": ["number", "null"]}
    metrics = {"type": "object", "additionalProperties": {"type": "number"}}
    grade = {
        "type": "object",
        "required": ["score", "metrics", "coverage"],
        "properties": {
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "metrics": metrics,
            "coverage": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "additionalProperties": False,
    }
    member_answer = {
        "type": "object",
        "required": ["model", "answer"],
        "properties": {"model": {"type": "string"}, "answer": {"type": "string"}},
        "additionalProperties": False,
    }
    return {
        "EvaluationEvent": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["schema", "type"],
                    "properties": {
                        "schema": {"const": "screamingface.evaluation-event.v1"},
                        "type": {"const": "accepted"},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["schema", "type", "elapsed_seconds"],
                    "properties": {
                        "schema": {"const": "screamingface.evaluation-event.v1"},
                        "type": {"const": "running"},
                        "elapsed_seconds": {"type": "number", "minimum": 0},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["schema", "type", "stage", "status", "label"],
                    "properties": {
                        "schema": {"const": "screamingface.evaluation-event.v1"},
                        "type": {"const": "progress"},
                        "stage": {
                            "type": "string",
                            "enum": ["dataset", "model", "grading", "aggregating"],
                        },
                        "status": {
                            "type": "string",
                            "enum": ["started", "completed"],
                        },
                        "label": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["schema", "type", "content_type", "value"],
                    "properties": {
                        "schema": {"const": "screamingface.evaluation-event.v1"},
                        "type": {"const": "complete"},
                        "content_type": {"const": "text/plain"},
                        "value": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["schema", "type", "status", "error"],
                    "properties": {
                        "schema": {"const": "screamingface.evaluation-event.v1"},
                        "type": {"const": "error"},
                        "status": {"type": "integer", "minimum": 400, "maximum": 599},
                        "error": {
                            "type": "object",
                            "required": ["code", "message"],
                            "properties": {
                                "code": {"type": "string"},
                                "message": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "additionalProperties": False,
                },
            ]
        },
        "Provider": {
            "type": "object",
            "required": ["id", "display_name", "auth_methods"],
            "properties": {
                "id": {"type": "string"},
                "display_name": {"type": "string"},
                "auth_methods": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["oauth", "api_key"]},
                    "minItems": 1,
                },
            },
            "additionalProperties": False,
        },
        "Model": {
            "type": "object",
            "required": ["id", "provider", "supported_tools", "required_connections"],
            "properties": {
                "id": {"type": "string"},
                "provider": {"type": "string"},
                "supported_tools": {"type": "array", "items": {"type": "string"}},
                "required_connections": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "additionalProperties": False,
        },
        "BenchmarkManifest": {
            "type": "object",
            "required": [
                "id",
                "title",
                "cases_route",
                "grader",
                "aggregator",
                "tools",
                "max_tool_calls",
                "tool_policy_route",
            ],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "cases_route": {"type": "string"},
                "grader": {"$ref": "#/components/schemas/BenchmarkStage"},
                "aggregator": {"$ref": "#/components/schemas/BenchmarkStage"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "max_tool_calls": {"type": ["integer", "null"], "minimum": 1, "maximum": 32},
                "tool_policy_route": nullable_string,
            },
            "additionalProperties": False,
        },
        "ToolPolicy": {
            "type": "object",
            "required": ["schema", "tools", "max_calls", "web_search"],
            "properties": {
                "schema": {"const": "screamingface.tool-policy.v1"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["web_search", "web_fetch"]},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "max_calls": {"type": "integer", "minimum": 1, "maximum": 32},
                "web_search": {
                    "oneOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "required": ["max_results", "include_domains", "exclude_domains"],
                            "properties": {
                                "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                                "include_domains": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "uniqueItems": True,
                                },
                                "exclude_domains": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "uniqueItems": True,
                                },
                            },
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "additionalProperties": False,
        },
        "ModelInput": {
            "type": "object",
            "required": ["schema", "question", "tool_policy"],
            "properties": {
                "schema": {"const": "screamingface.model-input.v1"},
                "question": {"type": "string", "minLength": 1},
                "tool_policy": {"$ref": "#/components/schemas/ToolPolicy"},
            },
            "additionalProperties": False,
        },
        "BenchmarkStage": {
            "type": "object",
            "required": ["kind", "route"],
            "properties": {"kind": {"type": "string"}, "route": {"type": "string"}},
            "additionalProperties": False,
        },
        "Registry": {
            "type": "object",
            "required": [
                "schema",
                "response_schemas",
                "limits",
                "providers",
                "models",
                "benchmarks",
                "reducers",
            ],
            "properties": {
                "schema": {"const": "screamingface.registry.v1"},
                "response_schemas": {"type": "array", "items": {"type": "string"}},
                "limits": {
                    "type": "object",
                    "properties": {"max_request_target_bytes": {"type": "integer", "minimum": 1}},
                    "required": ["max_request_target_bytes"],
                    "additionalProperties": False,
                },
                "providers": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Provider"},
                },
                "models": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Model"},
                },
                "benchmarks": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/BenchmarkManifest"},
                },
                "reducers": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        "Connection": {
            "type": "object",
            "required": ["provider", "status", "auth_method", "account_label"],
            "properties": {
                "provider": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["not_connected", "pending", "connected", "needs_reauth"],
                },
                "auth_method": {
                    "type": ["string", "null"],
                    "enum": ["oauth", "api_key", None],
                },
                "account_label": nullable_string,
            },
            "additionalProperties": False,
        },
        "ConnectionList": {
            "type": "object",
            "required": ["schema", "connections"],
            "properties": {
                "schema": {"const": "screamingface.connections.v1"},
                "connections": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Connection"},
                },
            },
            "additionalProperties": False,
        },
        "OAuthStart": {
            "type": "object",
            "required": ["provider", "status", "authorize_url", "expires_in"],
            "properties": {
                "provider": {"type": "string"},
                "status": {"const": "pending"},
                "authorize_url": {"type": "string", "format": "uri"},
                "expires_in": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "ApiKeyInput": {
            "type": "object",
            "required": ["api_key"],
            "properties": {"api_key": {"type": "string", "minLength": 8, "writeOnly": True}},
            "additionalProperties": False,
        },
        "RecipeResult": {
            "type": "object",
            "required": ["schema", "members", "answer"],
            "properties": {
                "schema": {"const": "screamingface.recipe-result.v1"},
                "members": {
                    "type": "object",
                    "additionalProperties": member_answer,
                    "minProperties": 1,
                },
                "answer": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "Grade": grade,
        "MemberGrade": {
            "allOf": [
                {"$ref": "#/components/schemas/Grade"},
                {
                    "type": "object",
                    "required": ["model"],
                    "properties": {"model": {"type": "string"}},
                },
            ]
        },
        "CaseGrade": {
            "type": "object",
            "required": ["schema", "benchmark_id", "case_id", "recipe", "members"],
            "properties": {
                "schema": {"const": CASE_GRADE_SCHEMA},
                "benchmark_id": {"type": "string"},
                "case_id": {"type": "string"},
                "recipe": {"$ref": "#/components/schemas/Grade"},
                "members": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/components/schemas/MemberGrade"},
                },
            },
            "additionalProperties": False,
        },
        "ReportMember": {
            "type": "object",
            "required": ["model", "score", "metrics"],
            "properties": {
                "model": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "metrics": metrics,
            },
            "additionalProperties": False,
        },
        "EvaluationFailure": {
            "type": "object",
            "required": ["case_id", "kind", "message", "status", "code"],
            "properties": {
                "case_id": {"type": "string"},
                "kind": {"type": "string"},
                "message": {"type": "string"},
                "status": {"type": ["integer", "null"]},
                "code": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "Report": {
            "type": "object",
            "required": [
                "schema",
                "benchmark_id",
                "case_ids",
                "n_cases",
                "n_scored",
                "coverage",
                "score",
                "baseline",
                "gain",
                "members",
                "metrics",
                "failures",
                "complete",
            ],
            "properties": {
                "schema": {"const": REPORT_SCHEMA},
                "benchmark_id": {"type": "string"},
                "case_ids": {"type": "array", "items": {"type": "string"}},
                "n_cases": {"type": "integer", "minimum": 1},
                "n_scored": {"type": "integer", "minimum": 0},
                "coverage": {"type": "number", "minimum": 0, "maximum": 1},
                "score": nullable_number,
                "baseline": nullable_number,
                "gain": nullable_number,
                "members": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/components/schemas/ReportMember"},
                },
                "metrics": metrics,
                "failures": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/EvaluationFailure"},
                },
                "complete": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "EngineError": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "additionalProperties": True,
                }
            },
            "additionalProperties": False,
        },
        "ConnectionError": {
            "type": "object",
            "required": ["schema", "code", "message", "provider", "retryable"],
            "properties": {
                "schema": {"const": "screamingface.error.v1"},
                "code": {"type": "string"},
                "message": {"type": "string"},
                "provider": nullable_string,
                "retryable": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }


def _tool_policy_reference() -> dict[str, object]:
    return {
        "versioned_route": "/benchmarks/{benchmark}/{version}/tool-policy",
        "document_schema": "screamingface.tool-policy.v1",
        "model_input_schema": "screamingface.model-input.v1",
        "inline_custom_policy": {
            "tools": "colon-separated unique IDs; web_search and/or web_fetch",
            "tools.max_calls": "required positive integer from 1 to 32 when tools is present",
            "search_prefix": "web_search.",
            "search_required": ["max_results"],
            "search_optional": ["include_domain.1..n", "exclude_domain.1..n"],
            "fetch_parameters": [],
        },
    }


def _identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


async def _send_json_error(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}, separators=(",", ":")).encode()
    await _send_response(send, status, body, b"application/json")


async def _send_response(
    send: Send,
    status: int,
    body: bytes,
    content_type: bytes,
) -> None:
    headers = [
        (b"content-type", content_type),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


_DOCS_HTML = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ScreamingFace engine · API reference</title>
  <style>
    :root {
      color-scheme: light;
      --paper: #ffffff;
      --ink: #17181a;
      --muted: #656a70;
      --line: #d9dde1;
      --soft: #f4f5f6;
      --gain: #278344;
      --mark: #a86c13;
      --blind: #bb3e35;
      --method: #174f7a;
    }
    html[data-theme="dark"] {
      color-scheme: dark;
      --paper: #111315;
      --ink: #f3f4f5;
      --muted: #a8adb3;
      --line: #353a40;
      --soft: #1a1d20;
      --gain: #70c483;
      --mark: #ddb362;
      --blind: #ef8177;
      --method: #7eb5dd;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "IBM Plex Sans", Inter, system-ui, sans-serif;
      font-size: 15px;
      line-height: 1.55;
    }
    button, code, pre, .mono, .method, .eyebrow, .state, .count {
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace;
    }
    a { color: inherit; }
    .rail {
      position: sticky;
      top: 0;
      z-index: 4;
      min-height: 44px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: var(--paper);
    }
    .wordmark { font-family: Rubik, system-ui, sans-serif; font-weight: 700; }
    .rail-actions { display: flex; align-items: center; gap: 18px; }
    .rail a, .rail button {
      border: 0;
      padding: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      text-decoration: none;
      cursor: pointer;
    }
    .layout { display: grid; grid-template-columns: 264px minmax(0, 1fr); }
    aside {
      position: sticky;
      top: 45px;
      height: calc(100vh - 45px);
      overflow: auto;
      border-right: 1px solid var(--line);
      padding: 28px 22px 60px;
    }
    aside h2, aside h3 {
      margin: 0 0 12px;
      font-size: 11px;
      letter-spacing: .09em;
      text-transform: uppercase;
      color: var(--muted);
    }
    aside h3 { margin-top: 26px; }
    nav { display: grid; }
    nav a {
      padding: 6px 0;
      color: var(--muted);
      text-decoration: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    nav a:hover { color: var(--ink); }
    main { width: min(1100px, 100%); padding: 54px 64px 100px; }
    h1 {
      max-width: 820px;
      margin: 0;
      font-family: "EB Garamond", Georgia, serif;
      font-size: clamp(42px, 6vw, 76px);
      font-weight: 500;
      line-height: .98;
      letter-spacing: -.035em;
    }
    h2 { margin: 72px 0 8px; font-size: 25px; line-height: 1.2; }
    h3 { margin: 0; font-size: 17px; }
    .eyebrow {
      margin-bottom: 14px;
      color: var(--mark);
      font-size: 11px;
      letter-spacing: .1em;
      text-transform: uppercase;
    }
    .lede { max-width: 800px; margin: 25px 0 0; color: var(--muted); font-size: 18px; }
    .meta {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-top: 48px;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }
    .metric { min-height: 104px; padding: 22px 20px 18px 0; }
    .metric + .metric { border-left: 1px solid var(--line); padding-left: 20px; }
    .metric strong { display: block; font-size: 24px; line-height: 1.1; }
    .metric span { display: block; margin-top: 8px; color: var(--muted); font-size: 12px; }
    .notice {
      margin-top: 34px;
      padding: 18px 20px;
      border-left: 3px solid var(--mark);
      background: var(--soft);
    }
    .notice strong { color: var(--mark); }
    .flow {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      margin-top: 24px;
      border: 1px solid var(--line);
    }
    .flow div { min-height: 92px; padding: 18px; }
    .flow div + div { border-left: 1px solid var(--line); }
    .flow small { display: block; color: var(--muted); margin-bottom: 8px; }
    .section-intro { max-width: 740px; color: var(--muted); }
    .operation { margin-top: 28px; border-top: 1px solid var(--line); }
    .operation-head {
      display: grid;
      grid-template-columns: 58px minmax(220px, 1fr) minmax(240px, 1.1fr);
      gap: 18px;
      align-items: baseline;
      padding: 18px 0 16px;
    }
    .method { color: var(--method); font-size: 12px; font-weight: 700; }
    .path { overflow-wrap: anywhere; font-size: 14px; }
    .summary { color: var(--muted); }
    .operation-body { padding: 0 0 26px 76px; }
    .description { max-width: 840px; margin: 0 0 18px; }
    details { border-top: 1px solid var(--line); }
    summary { padding: 11px 0; cursor: pointer; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 10px 12px 10px 0; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; }
    code { font-size: .9em; }
    pre {
      overflow: auto;
      margin: 0;
      padding: 16px;
      border: 1px solid var(--line);
      background: var(--soft);
      font-size: 12px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .state { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
    .state.current { color: var(--gain); }
    .state.planned { color: var(--mark); }
    .schema-list { margin-top: 24px; border-bottom: 1px solid var(--line); }
    .schema-list details { padding: 0; }
    .schema-list summary { font-family: "IBM Plex Mono", ui-monospace, monospace; }
    .error { color: var(--blind); }
    .loading { padding: 80px 0; color: var(--muted); }
    @media (max-width: 900px) {
      .layout { display: block; }
      aside { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
      aside nav { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }
      main { padding: 42px 24px 80px; }
      .meta { grid-template-columns: repeat(2, 1fr); }
      .metric:nth-child(3) { border-left: 0; }
      .flow { grid-template-columns: 1fr 1fr; }
      .flow div:nth-child(3) { border-left: 0; border-top: 1px solid var(--line); }
      .flow div:nth-child(4) { border-top: 1px solid var(--line); }
      .operation-head { grid-template-columns: 52px 1fr; }
      .summary { grid-column: 2; }
      .operation-body { padding-left: 70px; }
    }
    @media (max-width: 560px) {
      .rail { padding: 0 16px; }
      .rail-actions a { display: none; }
      aside { display: none; }
      .meta, .flow { grid-template-columns: 1fr; }
      .metric + .metric, .flow div + div { border-left: 0; border-top: 1px solid var(--line); padding-left: 0; }
      .operation-head { display: block; }
      .path, .summary { display: block; margin-top: 8px; }
      .operation-body { padding-left: 0; }
    }
  </style>
</head>
<body>
  <header class="rail">
    <div class="wordmark">screamingface</div>
    <div class="rail-actions">
      <a href="/openapi.json">OpenAPI JSON</a>
      <button id="theme" type="button">Dark mode</button>
    </div>
  </header>
  <div class="layout">
    <aside>
      <h2>Reference</h2>
      <nav id="overview-nav">
        <a href="#overview">Overview</a>
        <a href="#architecture">Architecture</a>
        <a href="#status">Current status</a>
        <a href="#capabilities">Capabilities</a>
        <a href="#schemas">Schemas</a>
      </nav>
      <h3>Operations</h3>
      <nav id="operations-nav"></nav>
    </aside>
    <main id="content"><div class="loading">Reading the running engine contract…</div></main>
  </div>
  <script>
    const root = document.documentElement;
    const themeButton = document.getElementById("theme");
    const savedTheme = localStorage.getItem("sf-docs-theme");
    if (savedTheme === "dark") root.dataset.theme = "dark";
    themeButton.textContent = root.dataset.theme === "dark" ? "Light mode" : "Dark mode";
    themeButton.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem("sf-docs-theme", root.dataset.theme);
      themeButton.textContent = root.dataset.theme === "dark" ? "Light mode" : "Dark mode";
    });

    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
    const idFor = (value) => String(value).replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
    const schemaText = (value) => JSON.stringify(value, null, 2);
    const responseSchema = (response) => {
      const content = response?.content || {};
      const media = Object.keys(content)[0];
      return media ? { media, ...content[media] } : null;
    };
    const parameterTable = (parameters = []) => parameters.length ? `
      <details open><summary>Parameters · ${parameters.length}</summary>
        <table><thead><tr><th>Name</th><th>Location</th><th>Required</th><th>Description</th></tr></thead>
        <tbody>${parameters.map((item) => `<tr><td><code>${escapeHtml(item.name)}</code></td><td>${escapeHtml(item.in)}</td><td>${item.required ? "yes" : "no"}</td><td>${escapeHtml(item.description)}</td></tr>`).join("")}</tbody></table>
      </details>` : "";
    const responseTable = (responses = {}) => `
      <details><summary>Responses · ${Object.keys(responses).length}</summary>
        <table><thead><tr><th>Status</th><th>Description</th><th>Media</th></tr></thead>
        <tbody>${Object.entries(responses).map(([status, response]) => {
          const resolved = responseSchema(response);
          return `<tr><td><code>${escapeHtml(status)}</code></td><td>${escapeHtml(response.description)}</td><td>${escapeHtml(resolved?.media || "—")}</td></tr>`;
        }).join("")}</tbody></table>
      </details>`;
    const requestBody = (operation) => operation.requestBody ? `
      <details><summary>Request body</summary><pre>${escapeHtml(schemaText(operation.requestBody))}</pre></details>` : "";
    const operationView = (path, method, operation, sharedParameters = []) => {
      const id = idFor(`${method}-${path}`);
      const parameters = [...sharedParameters, ...(operation.parameters || [])];
      return `<article class="operation" id="${id}">
        <div class="operation-head">
          <span class="method">${escapeHtml(method.toUpperCase())}</span>
          <code class="path">${escapeHtml(path)}</code>
          <span class="summary">${escapeHtml(operation.summary)}</span>
        </div>
        <div class="operation-body">
          <p class="description">${escapeHtml(operation.description)}</p>
          ${parameterTable(parameters)}
          ${requestBody(operation)}
          ${responseTable(operation.responses)}
        </div>
      </article>`;
    };

    fetch("/openapi.json", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((spec) => {
        const operations = [];
        for (const [path, pathItem] of Object.entries(spec.paths)) {
          const shared = pathItem.parameters || [];
          for (const method of ["get", "post", "put", "delete", "patch"]) {
            if (pathItem[method]) operations.push({ path, method, operation: pathItem[method], shared });
          }
        }
        const models = spec["x-screamingface-url4"].registry.models;
        const providers = spec["x-screamingface-url4"].registry.providers;
        const benchmarks = spec["x-screamingface-url4"].registry.benchmarks;
        const schemas = spec.components.schemas;
        const draco = spec["x-screamingface-status"].draco;
        document.getElementById("operations-nav").innerHTML = operations
          .map(({ path, method }) => `<a href="#${idFor(`${method}-${path}`)}"><span class="method">${escapeHtml(method)}</span> ${escapeHtml(path)}</a>`)
          .join("");
        document.getElementById("content").innerHTML = `
          <section id="overview">
            <div class="eyebrow">OpenAPI 3.1 · current executable contract</div>
            <h1>${escapeHtml(spec.info.title)}</h1>
            <p class="lede">${escapeHtml(spec.info.description)}</p>
            <div class="meta">
              <div class="metric"><strong>${escapeHtml(spec.info.version)}</strong><span>engine version</span></div>
              <div class="metric"><strong>${operations.length}</strong><span>documented operations</span></div>
              <div class="metric"><strong>${models.length}</strong><span>startup model routes</span></div>
              <div class="metric"><strong>${providers.length}</strong><span>connection providers</span></div>
            </div>
            <div class="notice"><strong>Local-first control plane.</strong> Connection endpoints are appropriate for the current researcher-owned engine. A hosted multi-user deployment needs an identity and credential-isolation boundary.</div>
          </section>
          <section id="architecture">
            <h2>Request boundary</h2>
            <p class="section-intro">The SDK constructs a complete URL4 expression. Only the ScreamingFace engine receives it; AI Gateway remains an internal model transport.</p>
            <div class="flow">
              ${spec["x-screamingface-architecture"].request_flow.map((step, index) => `<div><small>0${index + 1}</small>${escapeHtml(step)}</div>`).join("")}
            </div>
            <pre style="margin-top:20px">GET /v1?q=&lt;percent-encoded URL4 expression&gt;\nAccept: text/event-stream\n\naccepted → dataset/model/grading/aggregation progress → complete</pre>
          </section>
          <section id="status">
            <h2>Contract status</h2>
            <p><span class="state current">Executable now</span> · GPQA, dynamic model calls, majority vote, exact-choice grading, mean aggregation, connection control, and provider-neutral web tooling on advertised model routes.</p>
            <p><span class="state planned">Planned</span> · DRACO is not advertised or executable yet. ${escapeHtml(draco.blocking_capability)}</p>
          </section>
          <section id="capabilities">
            <h2>Executable capability registry</h2>
            <p class="section-intro">This is the live startup snapshot—not a hand-maintained model promise. Provider connection methods remain explicit engine policy until AI Gateway exposes protected provider discovery.</p>
            <h3 style="margin-top:26px">Providers</h3>
            <table><thead><tr><th>ID</th><th>Name</th><th>Authentication</th></tr></thead>
              <tbody>${providers.map((provider) => `<tr><td><code>${escapeHtml(provider.id)}</code></td><td>${escapeHtml(provider.display_name)}</td><td>${escapeHtml(provider.auth_methods.join(" · "))}</td></tr>`).join("")}</tbody>
            </table>
            <h3 style="margin-top:34px">Models</h3>
            <table><thead><tr><th>Route ID</th><th>Provider</th><th>Engine tools</th></tr></thead>
              <tbody>${models.map((model) => `<tr><td><code>/${escapeHtml(model.id)}</code></td><td>${escapeHtml(model.provider)}</td><td>${escapeHtml(model.supported_tools.join(" · ") || "—")}</td></tr>`).join("")}</tbody>
            </table>
            <h3 style="margin-top:34px">Benchmarks</h3>
            <table><thead><tr><th>ID</th><th>Cases</th><th>Grader</th><th>Aggregator</th></tr></thead>
              <tbody>${benchmarks.map((benchmark) => `<tr><td><code>${escapeHtml(benchmark.id)}</code></td><td><code>${escapeHtml(benchmark.cases_route)}</code></td><td><code>${escapeHtml(benchmark.grader.route)}</code></td><td><code>${escapeHtml(benchmark.aggregator.route)}</code></td></tr>`).join("")}</tbody>
            </table>
            <h3 style="margin-top:34px">Web tool policy</h3>
            <pre>${escapeHtml(schemaText(spec["x-screamingface-url4"].tools))}</pre>
          </section>
          <section id="schemas">
            <h2>Wire schemas</h2>
            <p class="section-intro">Direct URL4 success bodies remain <code>text/plain</code>. The SDK receives that same value in the terminal <code>complete</code> SSE event, then parses JSON-shaped values into the strict schemas below.</p>
            <div class="schema-list">
              ${Object.entries(schemas).map(([name, schema]) => `<details><summary>${escapeHtml(name)}</summary><pre>${escapeHtml(schemaText(schema))}</pre></details>`).join("")}
            </div>
          </section>
          <section id="operations">
            <h2>HTTP and URL4 route surface</h2>
            <p class="section-intro">The Python SDK normally uses <code>/v1</code>. The model, data, reducer, grader, and aggregator paths below are URL4 node routes composed inside that expression.</p>
            ${operations.map(({ path, method, operation, shared }) => operationView(path, method, operation, shared)).join("")}
          </section>`;
      })
      .catch((error) => {
        document.getElementById("content").innerHTML = `<p class="error">Could not read the engine contract: ${escapeHtml(error.message)}</p>`;
      });
  </script>
</body>
</html>
"""


__all__ = ["DOCS_PATH", "OPENAPI_PATH", "DocumentationASGI", "openapi_document"]
