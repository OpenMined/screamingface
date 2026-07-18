"""Path-qualified self-holdings — URL4 spec §5.6.1 / §5.6.3.1.

STORY: as an operator I declare several `@` shelves on my node and address one
per request by qualifying the eval path — `GET /v1/science?q=(@)!'…'` scopes a
bare `@` to the "science" shelf. The grammar is untouched: `self-ref = "@"`
(§5.6.2) takes no collection suffix, so the qualifier travels in the PATH, and
`@/science` remains a parse error by design.

INVARIANT: the qualifier is per-REQUEST state. It lives on `ExecutionContext`,
never on the node — a `Url4Node` serves concurrent requests, so a "current
collection" attribute on the node would be a data race.
"""

from __future__ import annotations

import pytest

from url4 import StaticIOLayer
from url4._serve import ConfigError, ProviderSpec, ServeConfig, build_node
from url4.dag.node import ExecutionContext
from url4.errors import ParseError
from url4.grammar import parse
from url4.server import Url4Node

CMDS = {"/echo": ("cat",)}


def _node() -> Url4Node:
    return build_node(
        ServeConfig(
            commands=CMDS,
            holdings={
                None: ProviderSpec(value="DEFAULT-SHELF"),
                "science": ProviderSpec(value="SCIENCE-SHELF"),
                "drafts/2026": ProviderSpec(value="NESTED-SHELF"),
            },
            identities={"emily": {"notes": ProviderSpec(value="EMILY-NOTES")}},
        )
    )


# --- the grammar is unchanged ------------------------------------------------------


def test_bare_at_takes_no_collection_suffix() -> None:
    # Spec §5.6.2 `self-ref = "@"`, parsing rule 12. Guards against anyone
    # "fixing" this into `@/collection`, which would violate the protocol.
    with pytest.raises(ParseError):
        parse("@/science")
    assert parse("@") is not None


# --- dispatch: the path qualifier selects the shelf --------------------------------


@pytest.mark.asyncio
async def test_unqualified_eval_path_uses_default_shelf() -> None:
    assert "DEFAULT-SHELF" in await _node().fetch("/v1?q=(@)!''", relative=True)


@pytest.mark.asyncio
async def test_path_qualifier_selects_the_shelf() -> None:
    assert "SCIENCE-SHELF" in await _node().fetch("/v1/science?q=(@)!''", relative=True)


@pytest.mark.asyncio
async def test_multi_segment_qualifier_joins_with_slash() -> None:
    assert "NESTED-SHELF" in await _node().fetch("/v1/drafts/2026?q=(@)!''", relative=True)


@pytest.mark.asyncio
async def test_undeclared_qualifier_falls_back_to_default_shelf() -> None:
    # Node semantics: exact collection, then the default shelf.
    assert "DEFAULT-SHELF" in await _node().fetch("/v1/absent?q=(@)!''", relative=True)


@pytest.mark.asyncio
async def test_qualifier_does_not_leak_into_identity_refs() -> None:
    # §5.6.2: the path qualifier scopes the NODE context; an identity-collection
    # scopes within the principal's holdings. `@emily/notes` keeps its own.
    out = await _node().fetch("/v1/science?q=(@, @emily/notes)!''", relative=True)
    assert "SCIENCE-SHELF" in out
    assert "EMILY-NOTES" in out


@pytest.mark.asyncio
async def test_qualifier_is_per_request_not_node_state() -> None:
    # Two requests against the SAME node instance must not see each other's
    # qualifier — the property that forced this onto ExecutionContext.
    node = _node()
    assert "SCIENCE-SHELF" in await node.fetch("/v1/science?q=(@)!''", relative=True)
    assert "DEFAULT-SHELF" in await node.fetch("/v1?q=(@)!''", relative=True)


@pytest.mark.asyncio
async def test_command_route_still_wins_its_exact_path() -> None:
    # Endpoints are matched before the qualifier branch.
    assert "hi" in await _node().fetch("/echo?q=(hi)!'go'", relative=True)


# --- context plumbing ---------------------------------------------------------------


def test_execution_context_defaults_to_no_collection() -> None:
    assert ExecutionContext(StaticIOLayer()).self_collection is None


def test_child_context_inherits_the_collection() -> None:
    ctx = ExecutionContext(StaticIOLayer(), self_collection="science")
    assert ctx.child(ctx.scope).self_collection == "science"


# --- config validation --------------------------------------------------------------


def test_routes_under_the_eval_path_are_rejected() -> None:
    # They would shadow every qualifier below that path.
    with pytest.raises(ConfigError, match="reserved for self-holdings qualifiers"):
        ServeConfig(commands={"/v1/science": ("cat",)}).validate()
    with pytest.raises(ConfigError, match="reserved for self-holdings qualifiers"):
        ServeConfig(commands=CMDS, data={"/v1/rows": ProviderSpec(value="x")}).validate()


def test_routes_outside_the_eval_path_are_fine() -> None:
    ServeConfig(commands=CMDS, data={"/rows": ProviderSpec(value="x")}).validate()
    # A different eval path moves the reserved namespace with it.
    ServeConfig(
        commands=CMDS, eval_path="/eval", data={"/v1/rows": ProviderSpec(value="x")}
    ).validate()
