"""mitmproxy addon — rewrites intercepted requests to the local ScreamingFace server.

This script runs inside the mitmdump subprocess. It receives the target host/port/scheme
via environment variables set by the parent plugin.
"""

import os

SF_HOST = os.environ.get("SF_HOST", "127.0.0.1")
SF_PORT = int(os.environ.get("SF_PORT", "8000"))
SF_SCHEME = os.environ.get("SF_SCHEME", "http")


class RewriteToScreamingFace:
    def request(self, flow):
        flow.request.host = SF_HOST
        flow.request.port = SF_PORT
        flow.request.scheme = SF_SCHEME


addons = [RewriteToScreamingFace()]
