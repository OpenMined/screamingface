"""Minimal direct-node HTTP server for deterministic URL4 transport tests."""

from __future__ import annotations

from screamingface._mock_engine import create_mock_url4_node


def main() -> None:
    create_mock_url4_node().serve(host="127.0.0.1", port=4404)


if __name__ == "__main__":
    main()
