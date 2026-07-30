"""Named integration requirements blocked on unpublished SF Engine contracts."""

from __future__ import annotations

import pytest


@pytest.mark.skip(
    reason=("SF Engine must publish the Benchmark manifest route and versioned schema")
)
def test_plan_resolves_a_pinned_benchmark_manifest() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=("SF Engine must publish the compatibility-profile route and versioned schema")
)
def test_run_checks_destination_compatibility_before_paid_work() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=("SF Engine must publish the per-Candidate URL4 benchmark compilation contract")
)
def test_plan_compiles_one_complete_url4_per_candidate() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine must publish Candidate cache identity, scope, independence, scheduling, "
        "storage, provenance, and capability rules"
    )
)
def test_candidate_runs_follow_the_published_cache_and_independence_contract() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(reason="SF Engine must publish the versioned Candidate-result schema")
def test_run_decodes_one_terminal_result_into_the_public_report() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine must publish existing-Run reauthorization, replay retention, "
        "and reconnect policy"
    )
)
def test_run_reconnects_and_replays_after_the_original_capability_expires() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine must publish heartbeat liveness, terminal-close, and unavailable-gap behavior"
    )
)
def test_run_detects_a_dead_websocket_and_enters_reconnect() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine must publish Caller Credential, identity/budget, Cloudflare, error, "
        "and trusted-local authentication contracts"
    )
)
def test_client_authenticates_the_researcher_without_exposing_run_capabilities() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(reason="SF Engine must publish model and Benchmark catalogue schemas")
def test_client_exposes_authoritative_model_and_benchmark_discovery() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(reason="SF Engine must publish provider-connection proxy routes and schemas")
def test_client_manages_provider_connections_only_through_the_engine() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason="the real executor must map stable SF operation identity to trace attribution"
)
def test_events_and_plan_graph_map_to_candidates_members_graders_and_tools() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine must publish cross-layer retry ownership, retryability, idempotency, "
        "and attempt-attribution contracts"
    )
)
def test_billable_operations_are_not_multiplied_by_layered_retries() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine or URL4 must publish ordered all-settled Fusion member outcomes and "
        "successful-only Reducer input"
    )
)
def test_fusion_reduces_successful_members_and_preserves_typed_failures() -> None:
    raise AssertionError("remove this skip only with the authoritative Engine contract")


@pytest.mark.skip(
    reason=(
        "SF Engine and Client must pass the pinned full-DRACO conformance fixture and live "
        "acceptance run before claiming production DRACO reproduction"
    )
)
def test_full_draco_matches_the_pinned_reference_protocol() -> None:
    raise AssertionError("remove this skip only with full reference and live conformance evidence")
