"""Controlled SF Engine protocol server for public Client contract tests."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass
class ProtocolState:
    """Observable protocol behavior, independent from Client internals."""

    attached: threading.Event = field(default_factory=threading.Event)
    started: threading.Event = field(default_factory=threading.Event)
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    http_auth_schemes: list[str | None] = field(default_factory=list)
    websocket_auth_scheme: str | None = None
    mode: Literal[
        "success",
        "heartbeat",
        "stop",
        "gap",
        "disconnect",
        "token_invalid_json",
        "token_malformed",
        "missing_preference",
        "missing_location",
        "start_error",
        "start_auth_error",
    ] = "success"


@dataclass(frozen=True)
class ProtocolServer:
    url: str
    state: ProtocolState


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: ProtocolState) -> None:
        self.state = state
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 — stdlib handler API
        self.server.state.http_auth_schemes.append(_authorization_scheme(self.headers))
        if self.path != "/token":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.server.state.mode == "token_invalid_json":
            self._raw(HTTPStatus.OK, b"not-json", media_type="application/json")
            return
        if self.server.state.mode == "token_malformed":
            self._json(HTTPStatus.OK, {"ticket": "not-a-token"})
            return
        self._json(HTTPStatus.OK, {"token": "test-capability"})

    def do_GET(self) -> None:  # noqa: N802 — stdlib handler API
        if self.headers.get("Upgrade", "").casefold() == "websocket":
            self._websocket()
        else:
            self._start()

    def _start(self) -> None:
        query = parse_qs(urlsplit(self.path).query)
        if urlsplit(self.path).path != "/" or "q" not in query:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self.server.state.attached.is_set():
            self._json(
                HTTPStatus.PRECONDITION_REQUIRED,
                {
                    "type": "websocket_not_attached",
                    "title": "WebSocket not attached",
                    "status": HTTPStatus.PRECONDITION_REQUIRED,
                    "detail": "Attach a WebSocket to the topic before starting the run.",
                },
                media_type="application/problem+json",
            )
            return
        if self._reject_start():
            return
        self.send_response(HTTPStatus.ACCEPTED)
        if self.server.state.mode != "missing_preference":
            self.send_header("Preference-Applied", "respond-async")
        if self.server.state.mode != "missing_location":
            self.send_header("Location", "/?topic=run_1")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.server.state.started.set()

    def _reject_start(self) -> bool:
        if self.server.state.mode == "start_error":
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "type": "runner_unavailable",
                    "title": "Runner unavailable",
                    "status": HTTPStatus.BAD_GATEWAY,
                    "detail": "The test runner is unavailable.",
                },
                media_type="application/problem+json",
            )
            return True
        if self.server.state.mode == "start_auth_error":
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "type": "capability_expired",
                    "title": "Capability expired",
                    "status": HTTPStatus.UNAUTHORIZED,
                    "detail": "The execution capability expired.",
                },
                media_type="application/problem+json",
            )
            return True
        return False

    def do_DELETE(self) -> None:  # noqa: N802 — stdlib handler API
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _json(
        self,
        status: HTTPStatus,
        value: object,
        *,
        media_type: str = "application/json",
    ) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, status: HTTPStatus, body: bytes, *, media_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _websocket(self) -> None:
        if not self._accept_websocket():
            return
        event = self._receive_event()
        if event is None:
            return
        self.server.state.inbound_events.append(event)
        if event.get("type") != "ai.url4.attach":
            return
        self.server.state.attached.set()
        if self.server.state.started.wait(timeout=2):
            self._stream_run()

    def _accept_websocket(self) -> bool:
        self.server.state.websocket_auth_scheme = _authorization_scheme(self.headers)
        key = self.headers.get("Sec-WebSocket-Key")
        if key is None:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return False
        accept = base64.b64encode(
            hashlib.sha1(f"{key}{_WEBSOCKET_GUID}".encode()).digest()
        ).decode()
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.send_header("Sec-WebSocket-Protocol", "cloudevents.json")
        self.end_headers()
        self.close_connection = True
        return True

    def _receive_event(self) -> dict[str, Any] | None:
        try:
            value = json.loads(_read_client_text_frame(self.rfile))
        except (AssertionError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _stream_run(self) -> None:
        mode = self.server.state.mode
        if mode == "stop":
            self._stream_stop()
            return
        if mode == "disconnect":
            _send_server_text_frame(self.wfile, json.dumps(_run_frames()[0]))
            return
        if mode == "gap":
            self._stream_gap()
            return
        if mode == "heartbeat":
            _send_server_text_frame(self.wfile, json.dumps(_heartbeat()))
        for frame in _run_frames():
            _send_server_text_frame(self.wfile, json.dumps(frame))

    def _stream_stop(self) -> None:
        _send_server_text_frame(self.wfile, json.dumps(_run_frames()[0]))
        event = self._receive_event()
        if event is not None:
            self.server.state.inbound_events.append(event)

    def _stream_gap(self) -> None:
        frames = _gap_frames()
        for frame in frames[:2]:
            _send_server_text_frame(self.wfile, json.dumps(frame))
        event = self._receive_event()
        if event is not None:
            self.server.state.inbound_events.append(event)
        for frame in frames[2:]:
            _send_server_text_frame(self.wfile, json.dumps(frame))


def _read_client_text_frame(stream: Any) -> str:
    first, second = stream.read(2)
    if first & 0x0F != 1 or not second & 0x80:
        raise AssertionError("expected one masked WebSocket text frame")
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", stream.read(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", stream.read(8))[0]
    mask = stream.read(4)
    payload = stream.read(length)
    return bytes(value ^ mask[index % 4] for index, value in enumerate(payload)).decode()


def _send_server_text_frame(stream: Any, value: str) -> None:
    payload = value.encode()
    if len(payload) < 126:
        header = bytes((0x81, len(payload)))
    elif len(payload) < 65536:
        header = bytes((0x81, 126)) + struct.pack("!H", len(payload))
    else:
        header = bytes((0x81, 127)) + struct.pack("!Q", len(payload))
    stream.write(header + payload)
    stream.flush()


def _run_frames() -> tuple[dict[str, object], ...]:
    return (
        _frame("ai.url4.started", {"url4": "(@)!'hello'"}, 1),
        _frame(
            "ai.url4.cost.usage",
            {
                "scope": "subtree",
                "gen_ai.provider.name": "test",
                "gen_ai.response.model": "provider/opus",
                "pricing_version": "test",
                "usage": {
                    "gen_ai.usage.input_tokens": 10,
                    "gen_ai.usage.output_tokens": 2,
                    "gen_ai.usage.cache_read_tokens": 0,
                    "gen_ai.usage.cache_creation_tokens": 0,
                    "gen_ai.usage.reasoning_tokens": 0,
                },
                "cost": {
                    "input_usd": "0.01",
                    "output_usd": "0.02",
                    "cache_read_usd": "0",
                    "cache_creation_usd": "0",
                    "reasoning_usd": "0",
                    "total_usd": "0.03",
                },
            },
            2,
        ),
        _frame(
            "ai.url4.result",
            {"body": "[test] done", "media_type": "text/plain"},
            3,
        ),
        _frame(
            "ai.url4.terminated",
            {"status": "succeeded", "error": None},
            4,
        ),
    )


def _gap_frames() -> tuple[dict[str, object], ...]:
    success = _run_frames()
    usage = dict(success[1])
    usage["sequence"] = "3"
    usage["id"] = "event_3"
    result = dict(success[2])
    result["sequence"] = "4"
    result["id"] = "event_4"
    terminated = dict(success[3])
    terminated["sequence"] = "5"
    terminated["id"] = "event_5"
    replayed = _frame(
        "ai.url4.log",
        {
            "severity_number": 9,
            "severity_text": "INFO",
            "body": "replayed",
            "attributes": {},
        },
        2,
    )
    return success[0], usage, replayed, usage, result, terminated


def _frame(kind: str, data: dict[str, object], sequence: int) -> dict[str, object]:
    return {
        "specversion": "1.0",
        "id": f"event_{sequence}",
        "source": "/trace/run_1/node/root",
        "subject": "run_1",
        "time": datetime.now(UTC).isoformat(),
        "type": kind,
        "datacontenttype": "application/json",
        "sequence": str(sequence),
        "sequencetype": "Integer",
        "data": data,
    }


def _heartbeat() -> dict[str, object]:
    return {
        "specversion": "1.0",
        "id": "heartbeat",
        "source": "/trace/run_1",
        "subject": "run_1",
        "time": datetime.now(UTC).isoformat(),
        "type": "ai.url4.heartbeat",
        "datacontenttype": "application/json",
        "data": {},
    }


def _authorization_scheme(headers: Any) -> str | None:
    value = headers.get("Authorization")
    if value:
        return value.split(" ", 1)[0]
    return "Cf-Access-Token" if headers.get("Cf-Access-Token") else None


@contextmanager
def protocol_server(
    *,
    mode: Literal[
        "success",
        "heartbeat",
        "stop",
        "gap",
        "disconnect",
        "token_invalid_json",
        "token_malformed",
        "missing_preference",
        "missing_location",
        "start_error",
        "start_auth_error",
    ] = "success",
) -> Iterator[ProtocolServer]:
    state = ProtocolState(mode=mode)
    server = _Server(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = str(server.server_address[0])
        port = int(server.server_address[1])
        yield ProtocolServer(url=f"http://{host}:{port}", state=state)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
