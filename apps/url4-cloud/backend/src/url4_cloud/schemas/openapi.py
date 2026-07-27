"""OpenAPI 3.1 authoring (spec §12): a rich ``info`` block + the CloudEvents component schemas.

FastAPI generates the REST paths from the routes; we override ``app.openapi`` to enrich the result
without post-editing the routes — merging the shared ``url4_streaming_protocol`` schemas into
``components.schemas`` so Scalar renders the full telemetry contract, and giving ``info`` the
title / markdown description / contact / license the §12 DOC-GATE requires.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from url4_cloud.auth import Problem
from url4_cloud.schemas.protocol_schemas import protocol_component_schemas

API_DESCRIPTION = """\
The **url4-cloud** control plane: mint a topic-capability JWT, open a WebSocket, then start a
url4 run whose telemetry streams back as **CloudEvents 1.0** frames (OTel `gen_ai.*` spans, logs,
and a separate `ai.url4.cost.usage` taxonomy event). REST is transactional (RFC 7240 sync/async,
RFC 9457 problems); the live stream is described by the companion **AsyncAPI** doc at
`/asyncapi.json`. See `docs/protocol.md` for the standards decision record.

## Execution flows

**Synchronous** — `GET /` holds until the terminal frame (bounded by `SYNC_MAX_WAIT`) and returns
the Result body:

![Synchronous execution](/diagrams/url4-cloud-execution-sync.svg)

**Asynchronous** — `Prefer: respond-async` returns `202` + `Location`/`Link` immediately; the
Result arrives on the WebSocket stream:

![Asynchronous execution](/diagrams/url4-cloud-execution-async.svg)

**Streaming · resume · cancel** — frames carry a monotonic `sequence`; a client can re-attach and
replay via `ai.url4.attach`, or cancel via `ai.url4.stop`:

![Streaming, resume and cancel](/diagrams/url4-cloud-execution-stream.svg)
"""

# WHY: only tags with in-schema REST operations — "Stream" (WS, AsyncAPI-only) and "Ops" (hidden
# routes) would render as empty sidebar sections in /scalar, so they are omitted (OME-566).
TAGS: list[dict[str, str]] = [
    {"name": "Token", "description": "Mint a topic-capability JWT (spec §4)."},
    {"name": "Execution", "description": "Start (sync/async) and stop a url4 run (spec §5)."},
    {"name": "Catalog", "description": "Discover the models a credential can address (OME-625)."},
]


def customize_openapi(app: FastAPI) -> None:
    """Install a cached ``app.openapi`` that emits the enriched OpenAPI 3.1 document."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary="Distributed url4 execution — REST control + CloudEvents telemetry.",
            description=API_DESCRIPTION,
            routes=app.routes,
            tags=TAGS,
            contact={"name": "OpenMined — ScreamingFace", "url": "https://screamingface.ai"},
            license_info={
                "name": "Apache-2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0",
            },
        )
        components = schema.setdefault("components", {})
        merged = protocol_component_schemas()
        merged.update(components.get("schemas", {}))  # keep FastAPI's own error schemas
        # WHY: the REST error responses reference RFC 9457 Problem by $ref under problem+json (no
        # FastAPI `model=`, which would force an application/json variant), so register the schema
        # here for the ref to resolve (OME-552).
        merged.setdefault("Problem", Problem.model_json_schema())
        components["schemas"] = merged
        # WHY: the per-run capability rides a dedicated URL4-Capability header (apiKey), decoupled
        # from `Authorization`; declare it so Scalar renders the header input and the execution ops
        # advertise the requirement (OME-556). WS auth is the `?ticket=` query param (§6).
        components.setdefault("securitySchemes", {})["URL4Capability"] = {
            "type": "apiKey",
            "in": "header",
            "name": "URL4-Capability",
            "description": "Per-run capability JWT (spec §4); bare token, not on Authorization.",
        }
        for method in ("get", "delete"):
            operation = schema.get("paths", {}).get("/", {}).get(method)
            if operation is not None:
                operation["security"] = [{"URL4Capability": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
