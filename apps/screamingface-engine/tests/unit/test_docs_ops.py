from fastapi.testclient import TestClient

from screamingface_engine.app import create_app

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
EXPECTED_SEND_COMMANDS = {"StopEvent", "AttachEvent"}


def _client() -> TestClient:
    return TestClient(create_app())


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
    schema = create_app().openapi()
    cost = schema["components"]["schemas"]["CostUsageData"]
    assert "example" not in cost
    examples = cost.get("examples")
    assert isinstance(examples, list) and examples, "CostUsageData must carry an `examples` array"
    sample = examples[0]
    assert sample["scope"] == "self"
    assert sample["cost"]["total_usd"] == "0.0435"


def test_docs_page_serves_scalar_with_both_specs() -> None:
    resp = _client().get("/docs")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/openapi.json" in body
    assert "/asyncapi.json" in body


def test_scalar_page_serves_openapi_reference() -> None:
    resp = _client().get("/scalar")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/openapi.json" in body


def test_asyncapi_page_serves_asyncapi_reference() -> None:
    resp = _client().get("/asyncapi")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/asyncapi.json" in body


def test_openapi_tags_omit_empty_stream_and_ops() -> None:
    schema = create_app().openapi()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    assert "Stream" not in tag_names
    assert "Ops" not in tag_names
    assert {"Token", "Execution"} <= tag_names
    assert "/healthz" not in schema["paths"]


def test_asyncapi_document_describes_the_ws_channel() -> None:
    resp = _client().get("/asyncapi.json")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["asyncapi"].startswith("3.0")
    channels = doc["channels"]
    (channel,) = channels.values()
    assert channel["address"] == "/ws"
    assert channel["messages"], "the /ws channel must list its messages"
    actions = {op["action"] for op in doc["operations"].values()}
    assert actions == {"send", "receive"}
    msg_schemas = set(doc["components"]["schemas"])
    assert EXPECTED_EVENT_SCHEMAS <= msg_schemas


def test_asyncapi_receive_operation_includes_error() -> None:
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
    doc = _client().get("/asyncapi.json").json()
    (send_op,) = [op for op in doc["operations"].values() if op["action"] == "send"]
    sent = {ref["$ref"].rsplit("/", 1)[-1] for ref in send_op["messages"]}
    assert sent == EXPECTED_SEND_COMMANDS
    assert "ExecuteEvent" not in set(doc["components"]["schemas"])


def test_livez_and_readyz_return_200() -> None:
    client = _client()
    assert client.get("/livez").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_metrics_is_openmetrics_text_with_counters() -> None:
    client = _client()
    client.get("/livez")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "screamingface_engine_requests_total" in body


def test_execution_routes_document_responses() -> None:
    schema = create_app().openapi()
    get_resp = schema["paths"]["/"]["get"]["responses"]
    for code in ("200", "202", "400", "409", "428", "502", "504"):
        assert code in get_resp, f"GET / is missing documented response {code}"
    assert "Problem" in schema["components"]["schemas"], "RFC 9457 Problem must be a component"
    problem = get_resp["409"]["content"]["application/problem+json"]["schema"]
    assert problem["$ref"] == "#/components/schemas/Problem"
    headers = get_resp["202"]["headers"]
    assert {"Location", "Link", "Preference-Applied"} <= set(headers)
    del_resp = schema["paths"]["/"]["delete"]["responses"]
    assert "204" in del_resp
    ref = del_resp["403"]["content"]["application/problem+json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/Problem"


def test_get_documents_prefer_header_for_sync_async() -> None:
    op = create_app().openapi()["paths"]["/"]["get"]
    prefer = [p for p in op.get("parameters", []) if p["name"] == "Prefer" and p["in"] == "header"]
    assert prefer, "GET / must document the Prefer header parameter"
    assert "respond-async" in prefer[0].get("description", "")
    assert "async" in op.get("description", "").lower()


def test_execution_flow_diagrams_are_served() -> None:
    client = _client()
    for name in ("sync", "async", "stream"):
        resp = client.get(f"/diagrams/screamingface-engine-execution-{name}.svg")
        assert resp.status_code == 200, name
        assert resp.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in resp.text


def test_openapi_description_embeds_the_execution_diagrams() -> None:
    desc = create_app().openapi()["info"]["description"]
    assert "## Execution flows" in desc
    for name in ("sync", "async", "stream"):
        assert f"/diagrams/screamingface-engine-execution-{name}.svg" in desc


def test_openapi_declares_url4_capability_security_scheme() -> None:
    schema = create_app().openapi()
    scheme = schema["components"]["securitySchemes"]["URL4Capability"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "URL4-Capability"
    for method in ("get", "delete"):
        assert schema["paths"]["/"][method]["security"] == [{"URL4Capability": []}]
