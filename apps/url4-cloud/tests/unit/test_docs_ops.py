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


def test_docs_page_serves_scalar_with_both_specs() -> None:
    # OME-565: one canonical /docs Scalar reference with a document switcher over both specs — the
    # REST OpenAPI (default) and the AsyncAPI 3.0 stream, same-origin.
    resp = _client().get("/docs")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/openapi.json" in body
    assert "/asyncapi.json" in body


def test_scalar_page_serves_openapi_reference() -> None:
    # OME-566: /scalar + /asyncapi serve their own direct Scalar pages (no redirect).
    resp = _client().get("/scalar")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/openapi.json" in body


def test_asyncapi_page_serves_asyncapi_reference() -> None:
    # OME-566: /asyncapi renders the AsyncAPI doc directly — the WS channel + message list.
    resp = _client().get("/asyncapi")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "createApiReference" in body
    assert "/asyncapi.json" in body


def test_openapi_tags_omit_empty_stream_and_ops() -> None:
    # OME-566: "Stream" (WS — AsyncAPI-only) and "Ops" (hidden routes) have no REST operations, so
    # they'd render as empty /scalar sidebar sections. The REST doc keeps only populated tags, and
    # operational probes (incl. /healthz) stay out of the user-facing reference.
    schema = create_app().openapi()
    tag_names = {t["name"] for t in schema.get("tags", [])}
    assert "Stream" not in tag_names
    assert "Ops" not in tag_names
    assert {"Token", "Execution"} <= tag_names
    assert "/healthz" not in schema["paths"]


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


# --- REST response documentation (OME-552) --------------------------------


def test_execution_routes_document_responses() -> None:
    # GET / and DELETE / must document their real contract — status codes, the RFC 9457 Problem
    # schema (application/problem+json), and the 202 async-handle headers — so Scalar renders it
    # instead of the bare 200 FastAPI infers from a Response return (OME-552).
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
    # OME-555: the sync/async selector (RFC 7240 Prefer) is a documented header parameter, so Scalar
    # renders an input + explains the modes (it was read from raw headers, invisible in OpenAPI).
    op = create_app().openapi()["paths"]["/"]["get"]
    prefer = [p for p in op.get("parameters", []) if p["name"] == "Prefer" and p["in"] == "header"]
    assert prefer, "GET / must document the Prefer header parameter"
    assert "respond-async" in prefer[0].get("description", "")
    assert "async" in op.get("description", "").lower()


# --- execution-flow diagrams embedded in /scalar (OME-555) ----------------


def test_execution_flow_diagrams_are_served() -> None:
    # OME-555: the sync/async/streaming sequence diagrams ship in the image and are served
    # same-origin so Scalar renders them inside the OpenAPI description.
    client = _client()
    for name in ("sync", "async", "stream"):
        resp = client.get(f"/diagrams/url4-cloud-execution-{name}.svg")
        assert resp.status_code == 200, name
        assert resp.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in resp.text


def test_openapi_description_embeds_the_execution_diagrams() -> None:
    # OME-555: the three flows are embedded in the description as images, so /scalar renders them.
    desc = create_app().openapi()["info"]["description"]
    assert "## Execution flows" in desc
    for name in ("sync", "async", "stream"):
        assert f"/diagrams/url4-cloud-execution-{name}.svg" in desc


# --- capability security scheme (OME-556) ---------------------------------


def test_openapi_declares_url4_capability_security_scheme() -> None:
    # The per-run capability rides a dedicated URL4-Capability header (apiKey), decoupled from
    # Authorization — so Scalar renders the header input and the execution ops require it (OME-556).
    schema = create_app().openapi()
    scheme = schema["components"]["securitySchemes"]["URL4Capability"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "URL4-Capability"
    for method in ("get", "delete"):
        assert schema["paths"]["/"][method]["security"] == [{"URL4Capability": []}]
