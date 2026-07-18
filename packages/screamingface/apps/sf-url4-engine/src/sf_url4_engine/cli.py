"""Development server entrypoint for the ScreamingFace URL4 profile."""

from __future__ import annotations

import os

from sf_url4_engine.app import create_node


def main() -> None:
    host = os.environ.get("URL4_HOST", "127.0.0.1")
    port = int(os.environ.get("URL4_PORT", "4404"))
    create_node().serve(host=host, port=port)


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    main()
