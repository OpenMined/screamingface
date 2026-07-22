"""DOC-GATE + ops-endpoint behaviour (OME-523; spec §12, docs/protocol.md §9).

Headless: the app is built via ``create_app`` with no injected deps — the docs/ops surface
(OpenAPI enrichment, Scalar, AsyncAPI, k8s probes, OpenMetrics) is pure and needs no bus/k8s.
The DOC-GATE asserts the generated OpenAPI is authored to Scalar grade: every exposed component
schema is titled/described and ``CostUsageData`` carries a JSON-Schema ``examples`` array.
"""

from fastapi.testclient import TestClient

from url4_cloud.app import create_app

# The CloudEvents events that MUST surface as OpenAPI/AsyncAPI component schemas (protocol.md §4).
EXPECTED_EVENT_SCHEMAS = {
    "StartedEvent",
    "LogEvent",
    "SpanEvent",
    "CostUsageEvent",
    "HeartbeatEvent",
    "ResultEvent",
    "TerminatedEvent",
    "ErrorEvent",
    "StopEvent",
    "AttachEvent",
}
# INVARIANT: the WS inbound surface is Stop + Attach only — ai.url4.execute was dropped (OME-548).
EXPECTED_SEND_COMMANDS = {"StopEvent", "AttachEvent"}


def _client() -> TestClient:
    return TestClient(create_app())


# --- DOC-GATE: OpenAPI is Scalar-grade by construction --------------------


def test_openapi_is_3_1_with_rich_info() -> None:
    schema = create_app().openapi()
    assert schema["openapi"].startswith("3.1")
    info = schema["info"]
    assert info["title"]
    assert info["description"]
    assert info["version"]
    assert info["contact"]
    assert info["license"]


def test_every_component_schema_is_titled_or_described() -> None:
    schema = create_app().openapi()
    schemas = schema["components"]["schemas"]
    assert schemas, "expected component schemas to be present"
    offenders = [
        name for name, body in schemas.items() if not (body.get("title") or body.get("description"))
    ]
    assert offenders == [], f"component schemas lacking title/description: {offenders}"


def test_cloudevents_events_are_exposed_as_component_schemas() -> None:
    schema = create_app().openapi()
    schemas = schema["components"]["schemas"]
    missing = EXPECTED_EVENT_SCHEMAS - set(schemas)
    assert missing == set(), f"missing CloudEvents component schemas: {missing}"


def test_cost_usage_data_carries_examples() -> None:
    # JSON-Schema 2020-12 / OpenAPI 3.1 use the `examples` ARRAY; singular `example` is not a
    # 2020-12 keyword (validators ignore it), so the component must carry the conformant form
    # for Scalar's sample pane (OME-550).
    schema = create_app().openapi()
    cost = schema["components"]["schemas"]["CostUsageData"]
    assert "example" not in cost
    examples = cost.get("examples")
    assert isinstance(examples, list) and examples, "CostUsageData must carry an `examples` array"
    sample = examples[0]
    assert sample["scope"] == "self"
    assert sample["cost"]["total_usd"] == "0.0435"


# --- Scalar reference -----------------------------------------------------


def test_scalar_returns_html_referencing_openapi() -> None:
    resp = _client().get("/scalar")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "/openapi.json" in body
    assert "api-reference" in body


# --- AsyncAPI 3.0 for the /ws channel -------------------------------------


def test_asyncapi_document_describes_the_ws_channel() -> None:
    resp = _client().get("/asyncapi.json")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["asyncapi"].startswith("3.0")
    channels = doc["channels"]
    # exactly one channel, addressed at /ws, referencing the CloudEvents messages
    (channel,) = channels.values()
    assert channel["address"] == "/ws"
    assert channel["messages"], "the /ws channel must list its messages"
    # both directions have an operation (send = client->app, receive = app->client)
    actions = {op["action"] for op in doc["operations"].values()}
    assert actions == {"send", "receive"}
    # the CloudEvents events are the message payloads
    msg_schemas = set(doc["components"]["schemas"])
    assert EXPECTED_EVENT_SCHEMAS <= msg_schemas


def test_asyncapi_receive_operation_includes_error() -> None:
    # ai.url4.error is outbound telemetry — the client *receives* it, never sends it (OME-549).
    doc = _client().get("/asyncapi.json").json()
    ops = doc["operations"]
    (recv_op,) = [op for op in ops.values() if op["action"] == "receive"]
    (send_op,) = [op for op in ops.values() if op["action"] == "send"]
    received = {ref["$ref"].rsplit("/", 1)[-1] for ref in recv_op["messages"]}
    sent = {ref["$ref"].rsplit("/", 1)[-1] for ref in send_op["messages"]}
    assert "ErrorEvent" in received
    assert "ErrorEvent" not in sent
    assert "ErrorEvent" in doc["components"]["schemas"]


def test_asyncapi_send_operation_is_stop_and_attach_only() -> None:
    # The client-sent command set is exactly Stop + Attach; Execute is gone (OME-548).
    doc = _client().get("/asyncapi.json").json()
    (send_op,) = [op for op in doc["operations"].values() if op["action"] == "send"]
    sent = {ref["$ref"].rsplit("/", 1)[-1] for ref in send_op["messages"]}
    assert sent == EXPECTED_SEND_COMMANDS
    assert "ExecuteEvent" not in set(doc["components"]["schemas"])


# --- k8s probes -----------------------------------------------------------


def test_livez_and_readyz_return_200() -> None:
    client = _client()
    assert client.get("/livez").status_code == 200
    assert client.get("/readyz").status_code == 200


# --- OpenMetrics ----------------------------------------------------------


def test_metrics_is_openmetrics_text_with_counters() -> None:
    client = _client()
    # drive one request so the request counter has a sample
    client.get("/livez")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "url4_cloud_requests_total" in body
    assert "gen_ai_client_token_usage_total" in body
