"""Builds the AsyncAPI 3.0 document for the `/ws` telemetry channel: one CloudEvents 1.0
message per protocol event, split into the `receiveTelemetry` (app→client) and `sendCommand`
(client→app) operations. Served at `/asyncapi.json` as the companion to the OpenAPI doc."""

from typing import Any

from url4_cloud.schemas.protocol_schemas import (
    EVENT_TYPE,
    INBOUND_EVENTS,
    OUTBOUND_EVENTS,
    protocol_component_schemas,
)

ASYNCAPI_VERSION = "3.0.0"
CHANNEL = "stream"
CHANNEL_ADDRESS = "/ws"

INFO_DESCRIPTION = """\
The url4-cloud telemetry stream. One **CloudEvents 1.0** event per WebSocket message
(subprotocol `cloudevents.json`, docs/protocol.md §8). The client *receives* lifecycle/log/span/
cost/heartbeat/result/terminated events and *sends* stop/attach commands.
"""


def _messages_map(events: tuple[type, ...]) -> dict[str, dict[str, Any]]:
    """`$ref` each event name to its `components/messages` entry, for an operation's message
    list."""
    return {e.__name__: {"$ref": f"#/components/messages/{e.__name__}"} for e in events}


def _component_messages() -> dict[str, dict[str, Any]]:
    """Builds the `components/messages` map: one AsyncAPI message per protocol event, named by
    its CloudEvents `type` (`EVENT_TYPE`) and pointing at the matching `components/schemas`
    entry."""
    messages: dict[str, dict[str, Any]] = {}
    for event in (*OUTBOUND_EVENTS, *INBOUND_EVENTS):
        name = event.__name__
        messages[name] = {
            "name": EVENT_TYPE[name],
            "title": name,
            "contentType": "application/cloudevents+json",
            "payload": {"$ref": f"#/components/schemas/{name}"},
        }
    return messages


def build_asyncapi() -> dict[str, Any]:
    """Assembles the full AsyncAPI 3.0 document served at `/asyncapi.json`."""
    all_messages = {**_messages_map(OUTBOUND_EVENTS), **_messages_map(INBOUND_EVENTS)}
    return {
        "asyncapi": ASYNCAPI_VERSION,
        "info": {
            "title": "url4-cloud stream",
            "version": "0.1.0",
            "description": INFO_DESCRIPTION,
            "license": {
                "name": "Apache-2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0",
            },
        },
        "defaultContentType": "application/cloudevents+json",
        "servers": {
            "public": {
                "host": "cloud.screamingface.ai",
                "protocol": "wss",
                "pathname": CHANNEL_ADDRESS,
                "description": "The url4-cloud WebSocket bridge (CloudEvents structured mode).",
            }
        },
        "channels": {
            CHANNEL: {
                "address": CHANNEL_ADDRESS,
                "title": "url4 telemetry stream",
                "description": "CloudEvents 1.0 frames for one url4 run (topic = JWT `sub`).",
                "messages": all_messages,
            }
        },
        "operations": {
            "receiveTelemetry": {
                "action": "receive",
                "channel": {"$ref": f"#/channels/{CHANNEL}"},
                "summary": "Telemetry the client receives (app→client).",
                "messages": [
                    {"$ref": f"#/channels/{CHANNEL}/messages/{e.__name__}"} for e in OUTBOUND_EVENTS
                ],
            },
            "sendCommand": {
                "action": "send",
                "channel": {"$ref": f"#/channels/{CHANNEL}"},
                "summary": "Commands the client sends (client→app).",
                "messages": [
                    {"$ref": f"#/channels/{CHANNEL}/messages/{e.__name__}"} for e in INBOUND_EVENTS
                ],
            },
        },
        "components": {
            "messages": _component_messages(),
            "schemas": protocol_component_schemas(),
        },
    }
