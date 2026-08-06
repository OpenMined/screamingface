"""`CachePolicy` — per-run cache intent on the wire (plan Batch 1, spec §4.1/§4.2).

INVARIANT (spec §1.0): aigateway v2's cache-control grammar is **CLOSED to exactly one field**,
`use-cache`. Any other key inside a request body's `cache` object makes the WHOLE request
**bypass** — silently, with no error anywhere, even alongside a valid `use-cache: true`. So this
protocol type is `extra="forbid"`: a caller inventing `no_store` fails loudly HERE, at the url4
edge, instead of having it forwarded to a grammar whose only answer is to quietly cost every hit.

The type carries **intent only** (`participate`); the translation into aigateway's wire vocabulary
lives in `apps/url4-cloud` (plan §4), because `packages/url4` ships to SDK users and must not know
an adapter's request-body shape. `max_age` is url4-internal and is **never** sent upstream — v2
refuses it (`global_controls.py:79-83`).

WHY these tests live here and not in `packages/url4/tests`: `url4.streaming` ships from the url4
distribution but is gated by its only consumer — see the `[tool.coverage.run] omit` note in
`packages/url4/pyproject.toml`. Every other protocol test is in this directory.
"""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

import url4.streaming.protocol
from url4.streaming.protocol import (
    AttachData,
    AttachEvent,
    CachePolicy,
    InboundFrameAdapter,
    SpanData,
)


def _attach_frame(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "specversion": "1.0",
        "type": "ai.url4.attach",
        "id": "att",
        "source": "/client",
        "subject": "t",
        "data": data,
    }


# --- backward compatibility: STOP-THE-LINE -------------------------------------------


def test_attach_frame_without_cache_still_validates() -> None:
    """**Stop-the-line** (plan Batch 1 test 1). `AttachData` is a LIVE wire type — every client
    already in flight sends an attach frame with no `cache` key. If this fails, the field was
    made required and every existing client is broken; do not "fix" the test.
    """
    frame = InboundFrameAdapter.validate_python(_attach_frame({"from_sequence": 1}))

    assert isinstance(frame, AttachEvent)
    assert frame.data.from_sequence == 1
    assert frame.data.cache is None


def test_attach_frame_with_empty_data_still_validates() -> None:
    """The other half of the live-wire guard: an attach frame that states nothing at all."""
    frame = InboundFrameAdapter.validate_python(_attach_frame({}))

    assert isinstance(frame, AttachEvent)
    assert frame.data.from_sequence is None
    assert frame.data.cache is None


# --- "not stated" must stay distinguishable from an explicit opt-out ------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="cache-absent"),
        pytest.param({"cache": None}, id="cache-null"),
        pytest.param({"cache": {}}, id="cache-empty-object"),
    ],
)
def test_absent_null_and_empty_object_all_read_as_not_stated(data: dict[str, Any]) -> None:
    """Plan Batch 1 test 2. v2 treats absent / `null` / `{}` identically — all three mean
    "participate" — so all three must land on "not stated" rather than on a stated value.
    """
    attach = AttachData.model_validate(data)

    assert attach.cache is None or attach.cache.participate is None


def test_explicit_opt_out_is_distinguishable_from_not_stated() -> None:
    """The `None` vs `CachePolicy()` distinction is load-bearing (spec §3.1): collapsing them
    makes opt-out unexpressible and breaks D4's header-wins precedence, which can only fire when
    silence is distinguishable from a stated `False`.
    """
    stated = AttachData.model_validate({"cache": {"participate": False}})
    unstated = AttachData.model_validate({"cache": {}})

    assert stated.cache is not None
    assert stated.cache.participate is False
    assert unstated.cache is not None
    assert unstated.cache.participate is None


def test_explicit_participate_true_is_also_stated() -> None:
    """`participate=True` is a statement, not the default — D4 must be able to see it."""
    policy = CachePolicy.model_validate({"participate": True})

    assert policy.participate is True


# --- round trip ----------------------------------------------------------------------


def test_inbound_adapter_round_trip_preserves_the_policy() -> None:
    """Plan Batch 1 test 3. The policy has to survive serialize → transport → parse, or the WS
    carrier delivers nothing.
    """
    original = InboundFrameAdapter.validate_python(
        _attach_frame({"from_sequence": 2, "cache": {"participate": False}})
    )
    revived = InboundFrameAdapter.validate_python(
        original.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
    )

    assert isinstance(revived, AttachEvent)
    assert revived.data.cache is not None
    assert revived.data.cache.participate is False
    assert revived.data.from_sequence == 2


def test_round_trip_preserves_max_age() -> None:
    """`max_age` is parsed at the HTTP edge (Batch 3) and applied at read-back (Batch 7); it has
    to survive the frame carrier too, or the two carriers stop being equivalent.
    """
    frame = InboundFrameAdapter.validate_python(
        _attach_frame({"cache": {"participate": True, "max_age": 60}})
    )
    revived = InboundFrameAdapter.validate_python(
        frame.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
    )

    assert isinstance(revived, AttachEvent)
    assert revived.data.cache is not None
    assert revived.data.cache.max_age == 60


def test_max_age_defaults_to_not_stated() -> None:
    """A policy that says nothing about freshness must not invent a bound."""
    assert CachePolicy().max_age is None


# --- the closed grammar: unknown keys fail HERE, not upstream -------------------------


@pytest.mark.parametrize(
    "unknown",
    [
        pytest.param({"no_store": True}, id="v1-no-store"),
        pytest.param({"no_cache": True}, id="v1-no-cache"),
        pytest.param({"s_maxage": 60}, id="v1-s-maxage"),
        pytest.param({"ttl": 60}, id="v1-ttl"),
        pytest.param({"use-cache": False}, id="aigateway-wire-vocabulary"),
        pytest.param({"participate": False, "no_store": True}, id="valid-plus-unknown"),
    ],
)
def test_cache_policy_rejects_unknown_fields(unknown: dict[str, Any]) -> None:
    """Plan Batch 1 test 4 — the correctness test, not a style one.

    Under v2 an unrecognised control key does not degrade to "ignored": it makes the request
    BYPASS, even next to a valid `use-cache: true`. A well-meant `no_store` would therefore opt
    the caller out for the WRONG reason and a well-meant `ttl` would lose caching altogether,
    with nothing raised anywhere. `extra="forbid"` moves that failure to the url4 edge, loudly.

    `use-cache` is in this list deliberately: it is *aigateway's* vocabulary. The protocol type
    speaks intent, and the translation belongs in the adapter (plan §4).
    """
    with pytest.raises(ValidationError):
        CachePolicy.model_validate(unknown)


def test_attach_frame_with_unknown_cache_key_is_rejected() -> None:
    """The guard has to hold through the frame, which is how a real caller reaches it."""
    with pytest.raises(ValidationError):
        InboundFrameAdapter.validate_python(_attach_frame({"cache": {"no_store": True}}))


def test_cache_policy_has_exactly_the_two_designed_fields() -> None:
    """Pin the field set. A third field added without a design decision is how the closed
    grammar gets violated — and `max_age` is only safe because Batch 2 never forwards it.
    """
    assert set(CachePolicy.model_fields) == {"participate", "max_age"}


# --- the reporting half: SpanData ----------------------------------------------------


def test_span_data_without_cache_fields_still_validates() -> None:
    """Plan Batch 1 test 5. `SpanData` is emitted by every run today; the new fields must be
    optional or every existing producer breaks.
    """
    span = SpanData(name="chat", operation="chat", start=datetime(2026, 8, 5, 9, 0, 0))

    assert span.cache_status is None
    assert span.cache_reason is None


@pytest.mark.parametrize("status", ["hit", "miss", "bypass"])
def test_span_data_carries_cache_status_and_reason(status: str) -> None:
    """The three outcomes aigateway can report, plus its reason verbatim (spec §4.2)."""
    span = SpanData.model_validate(
        {
            "name": "chat",
            "gen_ai.operation.name": "chat",
            "start": datetime(2026, 8, 5, 9, 0, 0),
            "cache_status": status,
            "cache_reason": "opted_out",
        }
    )

    assert span.cache_status == status
    assert span.cache_reason == "opted_out"


def test_span_data_rejects_an_unknown_cache_status() -> None:
    """The status vocabulary is closed to what aigateway actually reports; a typo must not
    reach a dashboard as a fourth silent category.
    """
    with pytest.raises(ValidationError):
        SpanData.model_validate(
            {
                "name": "chat",
                "gen_ai.operation.name": "chat",
                "start": datetime(2026, 8, 5, 9, 0, 0),
                "cache_status": "stale",
            }
        )


def test_span_data_cache_fields_survive_the_wire() -> None:
    """`SpanData` dumps by alias; the cache fields carry no `gen_ai.*` alias (OTel has no
    semantic convention for them), so assert they still appear under their own names.
    """
    span = SpanData(
        name="chat",
        operation="chat",
        start=datetime(2026, 8, 5, 9, 0, 0),
        cache_status="hit",
        cache_reason="opted_out",
    )
    dumped = span.model_dump(mode="json", by_alias=True)
    revived = SpanData.model_validate(dumped)

    assert dumped["cache_status"] == "hit"
    assert revived.cache_status == "hit"
    assert revived.cache_reason == "opted_out"


# --- the export surface --------------------------------------------------------------


def test_cache_policy_is_exported_from_the_protocol_package() -> None:
    """url4-cloud imports the protocol as a package; a type reachable only by module path is
    not part of the contract.
    """
    assert url4.streaming.protocol.CachePolicy is CachePolicy
    assert "CachePolicy" in url4.streaming.protocol.__all__
