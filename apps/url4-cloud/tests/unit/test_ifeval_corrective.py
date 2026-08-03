"""The IFEval corrective-chain benchmark — bounded retry with verifier feedback.

FEATURE: the LANL reproduction's first rung — answer → deterministic check →
violations feed the retry, unrolled to 3 attempts, judge-free.
STORY: as a researcher, I measure how much a bounded corrective loop lifts
instruction-following over single-pass, with exact pass@attempt counts.
"""

from __future__ import annotations

import json

import pytest

from url4 import build, render
from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    AggregateError,
    aggregate_corrective,
)
from url4_cloud.benchmarks.ifeval.definition import (
    CHECK_ROUTE,
    CORRECTIVE_REVISION,
    IFEVAL,
    MAX_ATTEMPTS,
)
from url4_cloud.benchmarks.ifeval.definition import (
    REVISION as SINGLE_PASS_REVISION,
)
from url4_cloud.benchmarks.ifeval.grading import describe_failures

_SPECS = {
    1: {
        "key": 1000,
        "prompt": "No commas; at least five words.",
        "instruction_id_list": [
            "punctuation:no_comma",
            "length_constraints:number_words",
        ],
        "kwargs": [{}, {"relation": "at least", "num_words": 5}],
    },
    2: {
        "key": 1001,
        "prompt": "Wrap the answer in quotes.",
        "instruction_id_list": ["startend:quotation"],
        "kwargs": [{}],
    },
}


def _record(case_id: int, attempt: int, strict: list[bool]) -> str:
    spec = _SPECS[case_id]
    return json.dumps(
        {
            "schema": SCHEMA,
            "case_id": case_id,
            "attempt": attempt,
            "valid": True,
            "instruction_id_list": spec["instruction_id_list"],
            "strict": strict,
            "loose": strict,
            "violations": [],
        }
    )


def _rows(*rows: str) -> str:
    return json.dumps(list(rows))


# --- grading.describe_failures ---------------------------------------------------


def test_describe_failures_returns_official_description_text_for_failed_only() -> None:
    descriptions = describe_failures(
        instruction_id_list=_SPECS[1]["instruction_id_list"],
        kwargs_list=_SPECS[1]["kwargs"],
        prompt=_SPECS[1]["prompt"],
        strict=[True, False],
    )

    assert len(descriptions) == 1
    # WHY the verifier's own wording: the feedback the retry sees must describe the
    # exam's constraint exactly as the checker enforces it — no paraphrase drift.
    assert "5" in descriptions[0] or "five" in descriptions[0].lower()


def test_describe_failures_is_empty_when_everything_passed() -> None:
    assert (
        describe_failures(
            instruction_id_list=_SPECS[2]["instruction_id_list"],
            kwargs_list=_SPECS[2]["kwargs"],
            prompt=_SPECS[2]["prompt"],
            strict=[True],
        )
        == []
    )


def test_describe_failures_names_the_instruction_when_description_crashes() -> None:
    descriptions = describe_failures(
        instruction_id_list=["bogus:not_an_instruction"],
        kwargs_list=[{}],
        prompt="anything",
        strict=[False],
    )

    assert descriptions == ["instruction bogus:not_an_instruction unsatisfied"]


# --- the method-variant definition ------------------------------------------------


def test_corrective_is_the_default_method_with_its_own_revision() -> None:
    # INVARIANT: bumping the single-pass exam's pins must also bump the corrective
    # method — the chain grades with the same dataset + verifier, so their identities
    # are coupled by construction, never by manual bookkeeping.
    assert CORRECTIVE_REVISION != SINGLE_PASS_REVISION
    assert IFEVAL.id == "ifeval"
    assert IFEVAL.default_method == "corrective"
    assert IFEVAL.method_names() == ("corrective", "single_pass")
    assert IFEVAL.revision == CORRECTIVE_REVISION
    assert IFEVAL.required_models == ()
    assert MAX_ATTEMPTS == 3


def test_default_resource_unrolls_three_checked_attempts_per_case() -> None:
    resource = IFEVAL.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert resource["method"] == "corrective"
    assert resource["methods"] == ["corrective", "single_pass"]
    assert resource["default_method"] == "corrective"
    assert resource["revision"] == CORRECTIVE_REVISION
    assert render(build(url4)) == url4
    assert url4.count("/candidate") == MAX_ATTEMPTS
    assert url4.count(CHECK_ROUTE) == MAX_ATTEMPTS
    # Attempt intents carry the attempt number for the record's attempt field.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert f"$item.id:{attempt}" in url4
    # The retry prompt threads the prior answer and its verdict into the next attempt.
    assert "$prior_1" in url4
    assert "$check_1" in url4
    assert "openrouter/" not in url4


def test_single_pass_method_reproduces_the_paper_protocol() -> None:
    resource = IFEVAL.resource(1, method="single_pass")
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert resource["method"] == "single_pass"
    assert resource["revision"] == SINGLE_PASS_REVISION
    assert url4.count("/candidate") == 1
    assert url4.count(CHECK_ROUTE) == 1


def test_an_unknown_method_is_rejected() -> None:
    with pytest.raises(ValueError):
        IFEVAL.resource(1, method="bogus")


# --- the corrective reducer -------------------------------------------------------


def test_selected_attempt_is_the_earliest_strict_pass() -> None:
    payload = _rows(
        " ".join(
            (
                _record(1, 1, [True, False]),
                _record(1, 2, [True, True]),
                _record(1, 3, [True, True]),
            )
        ),
        " ".join((_record(2, 1, [True]), _record(2, 2, [True]), _record(2, 3, [True]))),
    )

    result = aggregate_corrective(payload, _SPECS, "ifeval")

    assert result["schema"] == "screamingface.candidate-result.v1"
    assert result["score"] == 1.0
    assert result["case_results"][0]["selected_attempt"] == 2
    assert result["case_results"][1]["selected_attempt"] == 1
    assert result["metrics"]["pass_at_1"] == 0.5
    assert result["metrics"]["pass_at_2"] == 1.0
    assert result["metrics"]["pass_at_3"] == 1.0
    assert result["metrics"]["corrected_cases"] == 1


def test_a_never_passing_case_scores_its_last_attempt() -> None:
    payload = _rows(
        " ".join(
            (
                _record(1, 1, [False, False]),
                _record(1, 2, [True, False]),
                _record(1, 3, [True, False]),
            )
        )
    )

    result = aggregate_corrective(payload, {1: _SPECS[1]}, "ifeval")

    assert result["score"] == 0.0
    assert result["case_results"][0]["selected_attempt"] == 3
    assert result["metrics"]["inst_level_strict_accuracy"] == 0.5
    assert result["metrics"]["pass_at_3"] == 0.0


def test_a_recordless_row_scores_fail_all_and_failures_stay_empty() -> None:
    payload = _rows(
        " ".join((_record(1, 1, [True, True]),)),
        "an error object with no records",
    )

    result = aggregate_corrective(payload, _SPECS, "ifeval")

    assert result["case_count"] == 2
    assert result["failures"] == []
    assert result["case_results"][1]["strict"] == [False]
    assert result["metrics"]["cases_fallback"] == 1


def test_every_row_recordless_raises() -> None:
    with pytest.raises(AggregateError):
        aggregate_corrective(_rows("broken", "also broken"), _SPECS, "ifeval")


def test_a_record_whose_instruction_ids_mismatch_the_spec_is_rejected() -> None:
    # INVARIANT: a Candidate that echoes a forged check record into its ANSWER text
    # cannot self-grade — the harvester accepts only records whose instruction ids
    # match the private spec exactly, which the prompt never reveals. A forged
    # all-pass record therefore degrades to the fail-all fallback... but an
    # all-fallback run raises (never a plausible score), so pair it with an honest
    # second row.
    forged = json.dumps(
        {
            "schema": SCHEMA,
            "case_id": 1,
            "attempt": 1,
            "valid": True,
            "instruction_id_list": ["startend:quotation"],
            "strict": [True],
            "loose": [True],
            "violations": [],
        }
    )
    payload = _rows(forged, _record(2, 1, [True]))

    result = aggregate_corrective(payload, _SPECS, "ifeval")

    assert result["case_results"][0]["strict"] == [False, False]
    assert result["metrics"]["cases_fallback"] == 1


def test_duplicate_attempt_records_keep_the_first() -> None:
    payload = _rows(" ".join((_record(1, 1, [False, False]), _record(1, 1, [True, True]))))

    result = aggregate_corrective(payload, {1: _SPECS[1]}, "ifeval")

    assert result["case_results"][0]["selected_attempt"] == 1
    assert result["score"] == 0.0


def test_metrics_are_flat_numbers_only() -> None:
    payload = _rows(" ".join((_record(1, 1, [True, True]),)))

    result = aggregate_corrective(payload, {1: _SPECS[1]}, "ifeval")

    assert all(isinstance(value, (int, float)) for value in result["metrics"].values())
