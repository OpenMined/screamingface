"""AsyncAPI 3.0 authoring for the ``/ws`` channel (spec §12, docs/protocol.md §4, §8).

Describes the single CloudEvents WebSocket channel over the same JSON-Schema set as the OpenAPI
doc: outbound events are *received* by the client (app→client), inbound commands are *sent* by the
client (client→app). Message payloads ``$ref`` the shared ``components.schemas`` so the REST and WS
contracts never drift.
"""

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
    """``{eventName: {$ref: #/components/messages/eventName}}`` for a channel's message list."""
    return {e.__name__: {"$ref": f"#/components/messages/{e.__name__}"} for e in events}


def _component_messages() -> dict[str, dict[str, Any]]:
    """One AsyncAPI message per event, its payload ``$ref``-ing the shared schema."""
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
    """The full AsyncAPI 3.0 document for the ``/ws`` CloudEvents channel."""
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
