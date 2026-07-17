"""CI-only URL4 node for executing the committed notebooks without provider calls."""

from __future__ import annotations

from url4 import Request, Url4Node
from url4_mock_model import answer

_ROUTES = {
    "/codex/gpt-5.5": "codex/gpt-5.5",
    "/gemini/2.5": "gemini-cli/gemini-2.5-pro",
    "/claude/sonnet-4.6": "anthropic/claude-sonnet-4-6",
}


def create_node() -> Url4Node:
    node = Url4Node("screamingface-notebook-tests")
    node.data("/healthz", "ok")
    for route, model_id in _ROUTES.items():
        node.endpoint(route)(_handler(model_id))
    return node


def _handler(model_id: str):
    async def handle(request: Request) -> str:
        return answer(model_id, request.intent)

    return handle


def main() -> None:
    create_node().serve(host="127.0.0.1", port=4404)


if __name__ == "__main__":
    main()
