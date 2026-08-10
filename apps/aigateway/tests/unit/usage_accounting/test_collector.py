"""OME-303 U2 — the request-scoped collector, its grouping fields and its isolation.

The collector is the only thing that knows how many provider sends happened. Plan §12
makes "one observed send can disappear from the record set" a stop condition, so these
tests are the cardinality contract.
"""

from __future__ import annotations

import asyncio

import pytest

from aigateway.core.usage_accounting import (
    SCHEMA_PROVIDER_ATTEMPT,
    TRANSPORT_LITELLM_ASYNC_HTTP_V1,
    ProviderUsageAccountingEvidence,
)
from aigateway.core.usage_accounting._collector import (
    RequestAccountingCollector,
    active_collector,
    bound_collector,
)


def _collector(provider: str = "openrouter") -> RequestAccountingCollector:
    return RequestAccountingCollector(
        provider=provider,
        requested_model=f"{provider}/some-model",
        transport=TRANSPORT_LITELLM_ASYNC_HTTP_V1,
    )


class _Req:
    """Stand-in for the httpx Request the hooks correlate on."""


class TestCardinality:
    def test_no_records_before_any_send(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        assert collector.records() == ()

    def test_one_send_one_record(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=200, raw_evidence={"id": "gen-1"})
        (record,) = collector.records()
        assert record.sequence == 1
        assert record.dispatch_index == 1
        assert record.attempt_index == 1
        assert record.http_status == 200
        assert record.as_json()["schema"] == SCHEMA_PROVIDER_ATTEMPT

    def test_hidden_transport_resend_is_a_second_send_in_the_same_dispatch(self) -> None:
        # LiteLLM 1.95 AsyncHTTPHandler.post() retries once on ConnectError by building a
        # replacement client and sending again. That is a SECOND observed admission.
        collector = _collector()
        collector.begin_dispatch()
        first, second = _Req(), _Req()
        collector.on_send_admitted(first)
        collector.on_send_admitted(second)
        collector.on_response_completed(second, status=200, raw_evidence={})
        records = collector.records()
        assert [r.sequence for r in records] == [1, 2]
        assert [r.dispatch_index for r in records] == [1, 1]
        assert [r.attempt_index for r in records] == [1, 2]

    def test_gateway_overload_retry_is_a_new_dispatch(self) -> None:
        # A gateway overload retry re-invokes the plugin, so it must be distinguishable
        # from the transport's own hidden resend above.
        collector = _collector()
        collector.begin_dispatch()
        first = _Req()
        collector.on_send_admitted(first)
        collector.on_response_completed(first, status=429, raw_evidence=None)
        collector.begin_dispatch()
        second = _Req()
        collector.on_send_admitted(second)
        collector.on_response_completed(second, status=200, raw_evidence={})
        records = collector.records()
        assert [r.sequence for r in records] == [1, 2]
        assert [r.dispatch_index for r in records] == [1, 2]
        assert [r.attempt_index for r in records] == [1, 1]

    def test_attempt_ids_are_unique(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        for _ in range(5):
            collector.on_send_admitted(_Req())
        ids = {record.attempt_id for record in collector.records()}
        assert len(ids) == 5

    def test_provider_response_id_reaches_the_public_record(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=200, raw_evidence={"id": "gen-1"})
        attempt_id = collector.open_records()[0][0]
        collector.apply_evidence(
            attempt_id,
            ProviderUsageAccountingEvidence(supported=True, provider_response_id="gen-1"),
        )
        assert collector.records()[0].provider_response_id == "gen-1"


class TestRedirects:
    def test_a_redirect_hop_collapses_into_one_record(self) -> None:
        # INVARIANT (§3.4): httpx fires the request hook once per redirect hop. A
        # redirect chain is ONE generation call and must not inflate the record count.
        collector = _collector()
        collector.begin_dispatch()
        first, hop = _Req(), _Req()
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first)
        collector.on_send_admitted(hop)
        collector.on_response_completed(hop, status=200, raw_evidence={"id": "gen-1"})
        (record,) = collector.records()
        assert record.redirect_hop_count == 1
        assert record.http_status == 200

    def test_two_hops_still_one_record(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        a, b, c = _Req(), _Req(), _Req()
        collector.on_send_admitted(a)
        collector.on_redirect_observed(a)
        collector.on_send_admitted(b)
        collector.on_redirect_observed(b)
        collector.on_send_admitted(c)
        collector.on_response_completed(c, status=200, raw_evidence={})
        (record,) = collector.records()
        assert record.redirect_hop_count == 2

    def test_a_resend_after_a_redirect_chain_is_still_a_new_send(self) -> None:
        # A redirect must not swallow a genuine second admission that follows it.
        collector = _collector()
        collector.begin_dispatch()
        a, b, c = _Req(), _Req(), _Req()
        collector.on_send_admitted(a)
        collector.on_redirect_observed(a)
        collector.on_send_admitted(b)
        collector.on_response_completed(b, status=200, raw_evidence={})
        collector.on_send_admitted(c)
        collector.on_response_completed(c, status=200, raw_evidence={})
        records = collector.records()
        assert len(records) == 2
        assert [r.redirect_hop_count for r in records] == [1, 0]


class TestLatency:
    def test_latency_is_null_when_no_body_completed(self) -> None:
        # §3.4: latency_ms means completed non-streaming body latency. An admitted send
        # that never produced a body has no provider latency to report.
        collector = _collector()
        collector.begin_dispatch()
        collector.on_send_admitted(_Req())
        (record,) = collector.records()
        assert record.latency_ms is None
        assert record.outcome == "indeterminate"

    def test_latency_is_populated_once_a_body_completed(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=200, raw_evidence={})
        (record,) = collector.records()
        assert record.latency_ms is not None
        assert record.latency_ms >= 0


class TestStatus:
    def test_dispatched_with_zero_observed_sends_is_partial_not_complete(self) -> None:
        # §7 U2 / §9.22 — a supported provider that dispatched but produced no observed
        # send must never render `complete` (it would claim zero cost) nor the cache-hit
        # `not_applicable` (no cache hit happened).
        collector = _collector()
        collector.begin_dispatch()
        assert collector.status() == "partial"

    def test_capture_is_complete_when_every_send_resolved_without_usage_evidence(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=200, raw_evidence={})
        assert collector.status() == "complete"

    def test_partial_when_the_collector_was_marked_incomplete(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=200, raw_evidence={})
        collector.mark_incomplete()
        assert collector.status() == "partial"

    def test_not_applicable_when_nothing_was_ever_dispatched(self) -> None:
        collector = _collector()
        assert collector.status() == "not_applicable"


class TestContextVarIsolation:
    def test_bound_collector_restores_the_previous_value(self) -> None:
        assert active_collector() is None
        collector = _collector()
        with bound_collector(collector):
            assert active_collector() is collector
        assert active_collector() is None

    def test_concurrent_requests_never_exchange_records(self) -> None:
        # INVARIANT: the handler is app-lifetime and SHARED. Only the ContextVar keeps
        # one caller's sends out of another caller's records.
        async def one(provider: str, sends: int) -> tuple[str, int]:
            collector = RequestAccountingCollector(
                provider=provider,
                requested_model=f"{provider}/m",
                transport=TRANSPORT_LITELLM_ASYNC_HTTP_V1,
            )
            with bound_collector(collector):
                collector.begin_dispatch()
                for _ in range(sends):
                    await asyncio.sleep(0)
                    seen = active_collector()
                    assert seen is not None
                    assert seen is collector
                    seen.on_send_admitted(_Req())
                await asyncio.sleep(0)
                return provider, len(collector.records())

        async def run() -> list[tuple[str, int]]:
            return list(
                await asyncio.gather(one("openrouter", 3), one("anthropic", 1), one("gemini", 2))
            )

        assert sorted(asyncio.run(run())) == [
            ("anthropic", 1),
            ("gemini", 2),
            ("openrouter", 3),
        ]

    def test_gateway_call_ids_differ_between_collectors(self) -> None:
        assert _collector().gateway_call_id != _collector().gateway_call_id


class TestSafety:
    def test_an_unknown_request_object_cannot_create_a_phantom_record(self) -> None:
        # A response hook for a send this collector never admitted (a stray shared-handler
        # callback) must be ignored, not invent an attempt.
        collector = _collector()
        collector.begin_dispatch()
        collector.on_response_completed(_Req(), status=200, raw_evidence={})
        assert collector.records() == ()

    def test_provider_owned_transport_cannot_publish_an_arbitrary_failure_code(self) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_send_failed(
            request,
            outcome="transport_error",
            failure_code="Bearer sk-provider-secret",
        )
        assert collector.records()[0].failure_code == "transport_error"
        assert "sk-provider-secret" not in str(collector.records()[0].as_json())

    @pytest.mark.parametrize("status", [None, "not-a-status", -1, 99, 600, True])
    def test_malformed_transport_status_never_reaches_a_record(self, status: object) -> None:
        collector = _collector()
        collector.begin_dispatch()
        request = _Req()
        collector.on_send_admitted(request)
        collector.on_response_completed(request, status=status, raw_evidence={})
        (record,) = collector.records()
        assert record.http_status is None


class _UrlReq:
    """Stand-in for the httpx Request the hooks see, carrying the URL they compare on."""

    def __init__(self, url: str) -> None:
        self.url = url


_ORIGIN = "https://provider.example/v1/chat/completions"
_TARGET = "https://elsewhere.example/v1/chat/completions"


class TestRedirectTargetMatching:
    """F4 — the fold must be bounded to the hop httpx actually intends to issue.

    ``awaiting_redirect_hop`` alone cannot tell a redirect hop from LiteLLM's hidden
    replacement-client resend of the ORIGINAL request: both look like "the request hook
    fired again while the previous send is unresolved". Folding the latter makes a real
    observed attempt disappear — plan §12's stop condition.
    """

    def test_a_hop_to_the_expected_target_still_collapses(self) -> None:
        # §3.4 preserved: a genuine redirect chain remains ONE generation call.
        collector = _collector()
        collector.begin_dispatch()
        first, hop = _UrlReq(_ORIGIN), _UrlReq(_TARGET)
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first, target=_TARGET)
        collector.on_send_admitted(hop)
        collector.on_response_completed(hop, status=200, raw_evidence={"id": "gen-1"})
        (record,) = collector.records()
        assert record.redirect_hop_count == 1
        assert record.http_status == 200

    def test_a_resend_that_is_not_the_expected_hop_gets_its_own_record(self) -> None:
        # The F4 trace: httpx resolved a redirect to `_TARGET`, then aborted the chain, so
        # LiteLLM resent the ORIGINAL request on a replacement client. Two real sends.
        collector = _collector()
        collector.begin_dispatch()
        first, resend = _UrlReq(_ORIGIN), _UrlReq(_ORIGIN)
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first, target=_TARGET)
        collector.on_send_admitted(resend)
        collector.on_response_completed(resend, status=200, raw_evidence={"id": "gen-2"})
        records = collector.records()
        assert len(records) == 2, "the resend was swallowed into the redirect record"
        assert [r.redirect_hop_count for r in records] == [0, 0]

    def test_an_unmatched_redirect_send_is_finalized_without_losing_capture(self) -> None:
        # Both admissions remain represented: the failed redirect chain is a transport
        # error and the resend is a separate successful attempt.
        collector = _collector()
        collector.begin_dispatch()
        first, resend = _UrlReq(_ORIGIN), _UrlReq(_ORIGIN)
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first, target=_TARGET)
        collector.on_send_admitted(resend)
        collector.on_response_completed(resend, status=200, raw_evidence={"id": "gen-2"})
        records = collector.records()
        assert [record.outcome for record in records] == ["transport_error", "succeeded"]
        assert records[0].failure_code == "transport_error"
        assert collector.status() == "complete"

    def test_an_unmatched_admission_clears_the_expectation(self) -> None:
        # Otherwise a THIRD send would fold into the same stale record, and the fold would
        # be unbounded: N resends, one record.
        collector = _collector()
        collector.begin_dispatch()
        first, second, third = _UrlReq(_ORIGIN), _UrlReq(_ORIGIN), _UrlReq(_ORIGIN)
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first, target=_TARGET)
        collector.on_send_admitted(second)
        collector.on_send_admitted(third)
        assert len(collector.records()) == 3

    def test_a_hop_recorded_without_a_target_still_collapses(self) -> None:
        # Back-compatible by design: a caller that records a redirect WITHOUT a resolvable
        # target cannot disprove the hop, so §3.4's collapse still applies. In production
        # the handler never takes this path — it declines to expect a hop it cannot name.
        collector = _collector()
        collector.begin_dispatch()
        first, hop = _UrlReq(_ORIGIN), _UrlReq(_TARGET)
        collector.on_send_admitted(first)
        collector.on_redirect_observed(first)
        collector.on_send_admitted(hop)
        (record,) = collector.records()
        assert record.redirect_hop_count == 1
