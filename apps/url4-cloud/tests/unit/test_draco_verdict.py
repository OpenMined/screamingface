"""DRACO criterion-verdict binding behavior."""

from __future__ import annotations

import json

from url4_cloud.benchmarks.draco import verdict as criterion_verdict


def test_a_valid_reply_is_bound_to_the_engine_known_criterion() -> None:
    record = criterion_verdict.bind(
        json.dumps(
            {
                "criterion_id": "model-invented-id",
                "explanation": "The requirement is present.",
                "criterion_status": "MET",
            }
        ),
        criterion_id="actual-id",
    )

    assert record == {
        "schema": "screamingface.criterion-verdict.v1",
        "criterion_id": "actual-id",
        "valid": True,
        "explanation": "The requirement is present.",
        "criterion_status": "MET",
    }


def test_fenced_or_prefixed_json_is_accepted_like_the_reference_harness() -> None:
    record = criterion_verdict.bind(
        'Here is the verdict:\n```json\n{"explanation":"No error.",'
        '"criterion_status":"UNMET"}\n```',
        criterion_id="negative-1",
    )

    assert record["valid"] is True
    assert record["criterion_id"] == "negative-1"
    assert record["criterion_status"] == "UNMET"


def test_invalid_replies_become_diagnostic_records_instead_of_command_failures() -> None:
    assert criterion_verdict.bind("", criterion_id="a1") == {
        "schema": "screamingface.criterion-verdict.v1",
        "criterion_id": "a1",
        "valid": False,
        "reason": "empty",
    }
    assert criterion_verdict.bind("not json", criterion_id="a1")["reason"] == "invalid_json"
    assert (
        criterion_verdict.bind('{"explanation":"x","criterion_status":"MAYBE"}', criterion_id="a1")[
            "reason"
        ]
        == "invalid_status"
    )
    assert (
        criterion_verdict.bind('{"criterion_status":"MET"}', criterion_id="a1")["reason"]
        == "invalid_shape"
    )
