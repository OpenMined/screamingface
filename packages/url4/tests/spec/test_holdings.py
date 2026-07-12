"""Spec §5.6 — node self-reference (`@`) and identity-reference (`@<id>`):
resolution through the holdings port, unsupported-adapter errors, pass-through."""

from __future__ import annotations

import pytest
from conftest import RecordingIOLayer

from url4 import StaticIOLayer, run
from url4.errors import ResolutionError


class HoldingsLayer:
    """Minimal adapter implementing the optional holdings port (contract #13)."""

    def __init__(self, value: str = "HOLDINGS") -> None:
        self.value = value
        self.calls: list[tuple[str | None, str | None]] = []

    async def fetch(self, target: str, *, relative: bool) -> str:
        raise ResolutionError(f"no fetch mapping for {target!r}")

    async def fetch_holdings(self, identity: str | None, collection: str | None) -> str:
        self.calls.append((identity, collection))
        return self.value


# --- resolution through the port (§5.6.3) ------------------------------------------


@pytest.mark.asyncio
async def test_self_reference_resolves_via_holdings_port() -> None:
    # §5.6.3.1 — `@` resolves to the node's own backing data
    io = HoldingsLayer("MY DATA")
    result = await run("(@)!'science articles'", io)
    assert io.calls == [(None, None)]
    assert "MY DATA" in result


@pytest.mark.asyncio
async def test_identity_reference_resolves_with_identity() -> None:
    # §5.6.3.2 — `@emily` resolves the principal's holdings
    io = HoldingsLayer("EMILY DATA")
    result = await run("(@emily)!'thoughts'", io)
    assert io.calls == [("emily", None)]
    assert "EMILY DATA" in result


@pytest.mark.asyncio
async def test_identity_reference_with_collection() -> None:
    # §5.6.2 — `@emily/notes` selects within the principal's holdings
    io = HoldingsLayer()
    await run("(@emily/notes)!'q'", io)
    assert io.calls == [("emily", "notes")]


@pytest.mark.asyncio
async def test_static_io_layer_holdings_map() -> None:
    # Contract: StaticIOLayer grows a holdings map — keys are "" (self, `@`),
    # "name" (`@name`), "name/coll" (`@name/coll`), "coll" (`@` + qualifier).
    io = StaticIOLayer({}, holdings={"": "SELF", "emily": "EMILY"})
    result = await run("(@)!'q'", io)
    assert "SELF" in result
    result = await run("(@emily)!'q'", io)
    assert "EMILY" in result


@pytest.mark.asyncio
async def test_self_alongside_external_source() -> None:
    # §5.6.5.1 "Self + context" pattern
    class Both(HoldingsLayer):
        async def fetch(self, target: str, *, relative: bool) -> str:
            return "EXT"

    io = Both("SELF")
    result = await run("(@, https://peer/x)!'compare'", io)
    assert "SELF" in result and "EXT" in result


# --- unsupported adapters (§5.6.6 / contract #13) -------------------------------------


@pytest.mark.asyncio
async def test_self_ref_without_port_support_fails() -> None:
    # Contract #13 — adapter without fetch_holdings → self_ref_on_non_url4
    with pytest.raises(ResolutionError) as exc_info:
        await run("(@)!'q'", StaticIOLayer())
    assert exc_info.value.code == "self_ref_on_non_url4"


@pytest.mark.asyncio
async def test_identity_ref_without_port_support_fails() -> None:
    # Contract #13 — identity_ref_on_non_url4
    with pytest.raises(ResolutionError) as exc_info:
        await run("(@emily)!'q'", StaticIOLayer())
    assert exc_info.value.code == "identity_ref_on_non_url4"


# --- pass-through in nested expressions (§5.6.3.1 / §5.6.3.2) --------------------------


@pytest.mark.asyncio
async def test_self_ref_passes_through_to_sub_request_verbatim() -> None:
    # §5.6.3.1 — a node MUST NOT resolve a self-reference addressed to another
    # node; `@` inside a relative expression's context travels in the q= payload.
    rec = RecordingIOLayer()
    await run("/claude(@)!'go'", rec)
    assert any("(@)" in target for target in rec.fetches)


@pytest.mark.asyncio
async def test_identity_ref_passes_through_verbatim() -> None:
    # §5.6.3.2 — `@johndoe` is scoped to the receiving node
    rec = RecordingIOLayer()
    await run("/thepost(@johndoe)!'science'", rec)
    assert any("@johndoe" in target for target in rec.fetches)
