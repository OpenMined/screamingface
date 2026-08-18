"""Customizes FastAPI's generated OpenAPI document: control-plane title/description/tags, the
protocol-event schemas shared with the AsyncAPI doc, the `Problem` (RFC 9457) schema, and the
capability-JWT security scheme applied to the `GET`/`DELETE /` operations."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from screamingface_engine.auth import Problem
from screamingface_engine.schemas.protocol_schemas import protocol_component_schemas

API_DESCRIPTION = """\
The **screamingface-engine** control plane: mint a topic-capability JWT, open a
WebSocket, then start a url4 run whose telemetry streams back as **CloudEvents 1.0**
frames (OTel `gen_ai.*` spans, logs, and a separate `ai.url4.cost.usage` taxonomy
event). REST is transactional (RFC 7240 sync/async, RFC 9457 problems); the live
stream is described by the companion **AsyncAPI** doc at `/asyncapi.json`. See
`docs/protocol.md` for the standards decision record.

## Execution flows

**Synchronous** — `GET /` holds until the terminal frame (bounded by `SYNC_MAX_WAIT`) and returns
the Result body:

![Synchronous execution](/diagrams/screamingface-engine-execution-sync.svg)

**Asynchronous** — `Prefer: respond-async` returns `202` + `Location`/`Link` immediately; the
Result arrives on the WebSocket stream:

![Asynchronous execution](/diagrams/screamingface-engine-execution-async.svg)

**Streaming · resume · cancel** — frames carry a monotonic `sequence`; a client can re-attach and
replay via `ai.url4.attach`, or cancel via `ai.url4.stop`:

![Streaming, resume and cancel](/diagrams/screamingface-engine-execution-stream.svg)

## Response caching

A run **participates in the gateway's response cache by default**: an identical call is answered
from the stored corpus instead of being dispatched to the provider again. Only *declining* is
explicit, and there are two carriers for it — one per execution flow above:

- **`Cache-Control` on this `GET /`** — `no-store` / `no-cache` decline, `max-age=<seconds>`
  states a freshness bound, `url4-use-cache` opts in explicitly. It is the standard RFC 9111
  field, deliberately, so an intermediary may read it and add to it; conflicting directives
  resolve to declining, and an unknown or malformed one is ignored. A cache directive is a hint
  about cost, never a term of the request, so it never fails a run.
- **`cache` on the `ai.url4.attach` frame** — the same intent stated when the WebSocket attaches,
  for a client that has no other request to hang a header on. Described in the companion
  **AsyncAPI** doc at `/asyncapi.json`.

**The header wins** when both carriers speak, and the overridden declaration is announced on the
stream as a `warn` `ai.url4.log` rather than dropped silently. The policy covers the **whole
run** — every leaf and every fan-out branch — because one url4 expression is many gateway calls
and a per-node intent is not expressible in the grammar.

The outcome comes back: every span carries `cache_status` (`hit` / `miss` / `bypass`) and
`cache_reason` in the gateway's own vocabulary, and the run publishes one summary `ai.url4.log`
with its hit, miss and bypass-by-reason totals. Nothing in that telemetry is labelled by cache
key, prompt or credential.
"""

TAGS: list[dict[str, str]] = [
    {"name": "Token", "description": "Mint a topic-capability JWT (spec §4)."},
    {"name": "Execution", "description": "Start (sync/async) and stop a url4 run (spec §5)."},
    {"name": "Catalog", "description": "Discover the models a credential can address (OME-625)."},
    {
        "name": "Connections",
        "description": "Connect provider credentials through the ScreamingFace Engine.",
    },
]


def customize_openapi(app: FastAPI) -> None:
    """Replaces `app.openapi` with a customizer that patches FastAPI's default schema in place.

    Follows FastAPI's own caching convention (`app.openapi_schema` memoizes the result on the
    app), so the merge/patch work below runs at most once per process.
    """

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
        merged.update(components.get("schemas", {}))
        merged.setdefault("Problem", Problem.model_json_schema())
        components["schemas"] = merged
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
