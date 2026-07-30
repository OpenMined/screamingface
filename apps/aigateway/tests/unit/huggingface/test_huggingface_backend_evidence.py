"""OME-631 (OME-479 §6.2): Hugging Face backend-conditional capability evidence.

FEATURE: per-backend tool and structured-output evidence in the detailed contract.
A Hugging Face gateway id pins ONE inference backend (``…:nscale``), and the public
router catalog records `supports_tools` / `supports_structured_output` per backend —
so two models served by the same router genuinely differ.

STORY: as an API consumer I ask /v1/model-parameters about
`huggingface/meta-llama/Llama-3.1-8B-Instruct:nscale` and learn that THIS backend
does not do function calling, instead of a router-wide answer that is true for some
other backend I am not routed to.

INVARIANT (§5.1): HF's catalog carries NO parameter list, so the sampling fields stay
labelled-static. The catalog's only capability facts are these two booleans.
INVARIANT (§5.3): silence stays silence. A flag the row omits, a row that is absent,
a backend that is absent, and an id that pins no backend all yield NO observation —
never a fabricated `unsupported`, never a fabricated `supported`.
"""

from __future__ import annotations

import json

import pytest

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryLimits,
    RawResponse,
)
from aigateway.plugins.huggingface_provider.discovery import (
    MODELS_URL,
    ROUTER_SOURCE,
    ROUTER_SOURCE_REVISION,
    discover_huggingface_snapshot,
    parse_router_capability_snapshot,
)
from aigateway.plugins.huggingface_provider.plugin import PLUGIN
from aigateway.plugins.huggingface_provider.settings import pinned_router_target

_LLAMA = "meta-llama/Llama-3.1-8B-Instruct"
_GPT_OSS = "openai/gpt-oss-120b"

# Representative slice of the verified live router shape (128 rows / 283 provider
# entries on 2026-07-27). Note what is REAL here and drives the whole unit:
#   - nscale and deepinfra DISAGREE about tools for the same model;
#   - cerebras does tools but NOT structured output — the two flags are independent;
#   - sambanova omits both flags, as 64 of 283 live entries do.
_CATALOG = {
    "data": [
        {
            "id": _LLAMA,
            "object": "model",
            "owned_by": "meta-llama",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "providers": [
                {
                    "provider": "nscale",
                    "status": "live",
                    "supports_tools": False,
                    "supports_structured_output": True,
                },
                {
                    "provider": "deepinfra",
                    "status": "live",
                    "supports_tools": True,
                    "supports_structured_output": True,
                },
                {"provider": "sambanova", "status": "live"},
            ],
        },
        {
            "id": _GPT_OSS,
            "object": "model",
            "owned_by": "openai",
            "providers": [
                {
                    "provider": "cerebras",
                    "status": "live",
                    "supports_tools": True,
                    "supports_structured_output": False,
                }
            ],
        },
    ]
}


def _params(snapshot) -> dict[str, str]:
    return {o.request_path: o.support for o in snapshot.model_observations}


def _tools(snapshot) -> dict[str, str]:
    return {o.tool_type: o.support for o in snapshot.tool_observations}


# --- projection: one flag, three published cells -----------------------------


def test_a_backend_that_does_tools_is_reported_supported_everywhere() -> None:
    # Owner decision (2026-07-27): ONE observed flag projects into all three cells
    # the document uses to talk about tools, so the document cannot contradict
    # itself. `tools`/`tool_choice` are request paths; `function` is a tool type.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="deepinfra"
    )
    assert _params(snapshot)["tools"] == "supported"
    assert _params(snapshot)["tool_choice"] == "supported"
    assert _tools(snapshot)["function"] == "supported"


def test_a_backend_that_does_not_do_tools_is_reported_unsupported_everywhere() -> None:
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="nscale"
    )
    assert _params(snapshot)["tools"] == "unsupported"
    assert _params(snapshot)["tool_choice"] == "unsupported"
    assert _tools(snapshot)["function"] == "unsupported"


def test_backends_of_the_same_model_can_disagree() -> None:
    # THE reason this unit exists: 11 of the 48 multi-backend models in the live
    # catalog have backends that disagree about tools. A router-wide verdict would
    # be wrong for one of them whichever way it was chosen.
    nscale = parse_router_capability_snapshot(_CATALOG, upstream_model_id=_LLAMA, backend="nscale")
    deepinfra = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="deepinfra"
    )
    assert _params(nscale)["tools"] != _params(deepinfra)["tools"]


def test_structured_output_is_an_independent_verdict() -> None:
    # cerebras/gpt-oss-120b is the live counter-example to "tools implies JSON
    # mode": it does tools and does NOT do structured output.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_GPT_OSS, backend="cerebras"
    )
    assert _params(snapshot)["tools"] == "supported"
    assert _params(snapshot)["response_format"] == "unsupported"


def test_structured_output_does_not_touch_the_tools_section() -> None:
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_GPT_OSS, backend="cerebras"
    )
    assert _tools(snapshot) == {"function": "supported"}


def test_every_observation_is_labelled_as_live_router_evidence() -> None:
    # §5.1 "labelled": a reader must be able to tell network-derived evidence from
    # the reviewed-static fallback, so this must NOT borrow huggingface:static.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="nscale"
    )
    assert {o.source for o in snapshot.model_observations} == {ROUTER_SOURCE}
    assert snapshot.source_revision == ROUTER_SOURCE_REVISION


def test_evidence_is_per_model_not_endpoint_scoped() -> None:
    # §5.1: the two evidence scopes stay in separate fields. This is per-MODEL
    # evidence, so populating endpoint_observations would let it outrank a future
    # model-scoped verdict in the overlay's precedence order.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="nscale"
    )
    assert snapshot.endpoint_observations == ()


# --- silence stays silence ---------------------------------------------------


def test_a_backend_row_without_flags_says_nothing() -> None:
    # 64 of 283 live entries omit these keys. Coercing that to False would invent
    # a negative the catalog never published.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="sambanova"
    )
    assert snapshot.model_observations == ()
    assert snapshot.tool_observations == ()


def test_an_absent_model_row_says_nothing() -> None:
    # google/gemma-2-2b-it is a SEEDED gateway model that the live router catalog
    # does not list — the reachable-but-unlisted case, not an outage.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id="google/gemma-2-2b-it", backend="featherless-ai"
    )
    assert snapshot.model_observations == ()
    assert snapshot.tool_observations == ()
    assert snapshot.source_revision == ROUTER_SOURCE_REVISION


def test_an_absent_backend_in_a_present_row_says_nothing() -> None:
    # Deliberately NOT closed-world (unlike the OpenRouter catalog): a row lists
    # the backends the router serves, and a backend missing from it is an unknown
    # deployment, not a capability denial.
    snapshot = parse_router_capability_snapshot(
        _CATALOG, upstream_model_id=_LLAMA, backend="not-a-backend"
    )
    assert snapshot.model_observations == ()


def test_a_malformed_document_says_nothing_and_does_not_raise() -> None:
    for catalog in (None, {}, {"data": "nope"}, {"data": [{"id": _LLAMA, "providers": "nope"}]}):
        snapshot = parse_router_capability_snapshot(
            catalog, upstream_model_id=_LLAMA, backend="nscale"
        )
        assert snapshot.model_observations == ()
        assert snapshot.tool_observations == ()


def test_a_non_boolean_flag_is_not_a_verdict() -> None:
    # WHY: "true" and 1 are the classic shapes a schema drift produces; only a
    # genuine JSON boolean is read as a verdict.
    snapshot = parse_router_capability_snapshot(
        {"data": [{"id": _LLAMA, "providers": [{"provider": "x", "supports_tools": "true"}]}]},
        upstream_model_id=_LLAMA,
        backend="x",
    )
    assert snapshot.model_observations == ()


# --- the shared predicate ----------------------------------------------------


def test_a_pinned_backend_is_the_discovery_target() -> None:
    assert pinned_router_target(f"huggingface/{_LLAMA}:nscale") == (_LLAMA, "nscale")


def test_an_id_that_pins_no_backend_has_no_target() -> None:
    # WHY: without a suffix the router picks a backend PER REQUEST, so no single
    # backend row is the truth about the next call. Reporting one would be a guess.
    assert pinned_router_target(f"huggingface/{_LLAMA}") is None


def test_a_malformed_id_has_no_target() -> None:
    for bad in (
        "openrouter/foo/bar:x",
        "huggingface/nscale/meta-llama/Llama-3.1-8B-Instruct",
        f"huggingface/{_LLAMA}:",
    ):
        assert pinned_router_target(bad) is None


# --- the declared source -----------------------------------------------------


def test_the_plugin_declares_the_router_before_fetching() -> None:
    ref = PLUGIN.chat_discovery_source(model=f"huggingface/{_LLAMA}:nscale")
    assert ref is not None
    assert (ref.source, ref.revision) == (ROUTER_SOURCE, ROUTER_SOURCE_REVISION)


def test_the_declaration_and_the_fetch_share_one_predicate() -> None:
    # INVARIANT: a provider that declares a source commits to answering with a
    # snapshot or a DiscoveryError. If these two disagreed, the runtime would see
    # "promised evidence, then NOT ATTEMPTED" — indistinguishable from an outage.
    unpinned = f"huggingface/{_LLAMA}"
    assert PLUGIN.chat_discovery_source(model=unpinned) is None


# --- the bounded fetch -------------------------------------------------------


class _FakeClient:
    def __init__(self, body: str, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.calls: list[str] = []

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.calls.append(url)
        return RawResponse(status=self.status, content_type="application/json", body=self.body)


@pytest.mark.asyncio
async def test_the_fetch_reads_the_fixed_public_catalog() -> None:
    client = _FakeClient(json.dumps(_CATALOG))
    snapshot = await discover_huggingface_snapshot(
        _LLAMA, backend="nscale", client=client, limits=DiscoveryLimits()
    )
    assert client.calls == [MODELS_URL]
    assert _params(snapshot)["tools"] == "unsupported"


@pytest.mark.asyncio
async def test_a_failed_fetch_propagates_instead_of_returning_empty() -> None:
    # §5.3: an empty snapshot means "reached it, nothing listed". A failure must
    # NOT wear that costume, or the cache stores an outage labelled fresh.
    client = _FakeClient("{}", status=503)
    with pytest.raises(DiscoveryError):
        await discover_huggingface_snapshot(_LLAMA, backend="nscale", client=client)


@pytest.mark.asyncio
async def test_the_plugin_hook_does_not_dial_for_an_unpinned_id() -> None:
    client = _FakeClient(json.dumps(_CATALOG))
    assert (
        await PLUGIN.discover_chat_parameter_snapshot(model=f"huggingface/{_LLAMA}", client=client)
        is None
    )
    assert client.calls == []
