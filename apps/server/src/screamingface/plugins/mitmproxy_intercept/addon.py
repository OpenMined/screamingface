"""mitmproxy addon — routes intercepted requests to the correct frontend.

This script runs inside the mitmdump subprocess.  It reads the domain→target
mapping from ~/.screamingface/frontends.json (written by frontend plugins)
to route each intercepted domain to the frontend that handles it.

Falls back to SF_HOST/SF_PORT/SF_SCHEME env vars when no mapping exists.
"""

import json
import logging
import os
import uuid

log = logging.getLogger(__name__)

FRONTENDS_FILE = os.path.expanduser("~/.screamingface/frontends.json")

# Fallback single-target (used when no frontends.json exists)
SF_HOST = os.environ.get("SF_HOST", "127.0.0.1")
SF_PORT = int(os.environ.get("SF_PORT", "8000"))
SF_SCHEME = os.environ.get("SF_SCHEME", "http")


def _load_domain_map() -> dict:
    """Load domain→{host, port, scheme} mapping from frontends.json."""
    try:
        with open(FRONTENDS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class RouteToFrontend:
    """Rewrite intercepted flows to the appropriate frontend based on domain."""

    def __init__(self) -> None:
        self.domain_map = _load_domain_map()
        if self.domain_map:
            log.info("Loaded frontend mapping: %s", list(self.domain_map.keys()))
        else:
            log.info("No frontend mapping — using fallback %s:%s", SF_HOST, SF_PORT)

    def request(self, flow) -> None:  # noqa: ANN001
        domain = flow.request.pretty_host
        target = self.domain_map.get(domain)

        # Inject a trace ID so the proxy can correlate spans across layers
        trace_id = uuid.uuid4().hex
        flow.request.headers["x-sf-trace-id"] = trace_id

        if target:
            # print() instead of log.info() — mitmdump may suppress info-level logs
            print(
                f"[E2E-TRACE] ADDON intercepted {domain}:{flow.request.port}"
                f" → routing to {target['host']}:{target['port']}"
                f" | trace={trace_id}"
            )
            flow.request.host = target["host"]
            flow.request.port = target["port"]
            flow.request.scheme = target["scheme"]
        else:
            # Fallback to single-target mode
            print(
                f"[E2E-TRACE] ADDON intercepted {domain}:{flow.request.port}"
                f" → fallback to {SF_HOST}:{SF_PORT}"
                f" | trace={trace_id}"
            )
            flow.request.host = SF_HOST
            flow.request.port = SF_PORT
            flow.request.scheme = SF_SCHEME


addons = [RouteToFrontend()]
