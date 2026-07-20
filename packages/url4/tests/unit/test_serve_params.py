"""Protocol-param forwarding to command backends (url4._serve).

STORY: as an operator I mount a command backend that needs the caller's
protocol params (`?temperature=0.7`), not just the intent and context — so the
argv template exposes the SAME surface a Python endpoint handler gets from
`Request`: `{intent}`, `{context}`, `{param:<name>}`, `{params}`. A command
route is then a first-class peer of a Python handler, not a degraded one.

# AIDEV-NOTE: these tests live in their own module rather than appended to
# test_serve_backends.py on purpose. The append-only gate (sdlc rule 5) diffs at
# FILE level, so it cannot distinguish an append from an edit — appending would
# turn the gate red and force a `--skip-append-only` run, making "were prior
# tests touched?" unanswerable from the gate output alone. Same precedent as
# test_serve_hardening.py (review round 2).
"""

from __future__ import annotations

import json

import pytest

from url4.cli._serve import ServeConfig, build_node, make_command_handler
from url4.peer.server import Request

pytestmark = pytest.mark.asyncio

# Echoes its own argv[1], so a substituted token is observable verbatim.
_ECHO_ARGV1 = ["python3", "-c", "import sys; sys.stdout.write(sys.argv[1])"]


def _req(params: dict[str, str], intent: str = "go") -> Request:
    return Request(path="/cmd", context="", intent=intent, params=params)


async def test_param_token_substitutes_decoded_param() -> None:
    handler = make_command_handler([*_ECHO_ARGV1, "t={param:temperature}"], timeout=5.0)
    assert await handler(_req({"temperature": "0.7"})) == "t=0.7"


async def test_param_token_absent_param_is_empty_string() -> None:
    handler = make_command_handler([*_ECHO_ARGV1, "t={param:temperature}"], timeout=5.0)
    assert await handler(_req({})) == "t="


async def test_param_token_accepts_dotted_names() -> None:
    handler = make_command_handler([*_ECHO_ARGV1, "{param:coord.rounds}"], timeout=5.0)
    assert await handler(_req({"coord.rounds": "3"})) == "3"


async def test_params_token_is_full_mapping_as_json() -> None:
    handler = make_command_handler([*_ECHO_ARGV1, "{params}"], timeout=5.0)
    out = await handler(_req({"temperature": "0.2", "reasoning": "low"}))
    assert json.loads(out) == {"reasoning": "low", "temperature": "0.2"}


async def test_substitution_is_single_pass_no_cascade() -> None:
    # SECURITY: tokens are recognized in the OPERATOR template only —
    # token-shaped text arriving in caller-influenced values stays literal
    # instead of cascading into a second substitution round.
    handler = make_command_handler([*_ECHO_ARGV1, "{intent}|{param:a}"], timeout=5.0)
    out = await handler(_req({"a": "{intent}"}, intent="{param:a}"))
    assert out == "{param:a}|{intent}"


async def test_params_reach_command_through_node_dispatch() -> None:
    # End-to-end: a nested canonical call carries ?temperature=…, the node
    # dispatches it to the endpoint, and the command receives the value.
    config = ServeConfig(commands={"/model": (*_ECHO_ARGV1, "T={param:temperature}")})
    node = build_node(config)
    result = await node.evaluate("(r=/model?temperature=0.7&q=(x)!'go')!'$r'")
    assert "T=0.7" in result.text
