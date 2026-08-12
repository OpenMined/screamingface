"""The IFEval corrective Benchmark — fixed retry with verifier feedback.

FEATURE: answer → deterministic check → sanitized violations feed the retry,
unrolled to 3 attempts and judge-free.
STORY: as a researcher, I measure how much a bounded corrective loop lifts
instruction-following over single-pass, with exact pass@attempt counts.
"""

from __future__ import annotations

import json

from url4 import build, render
from url4_cloud.benchmarks.ifeval.aggregate import (
    SCHEMA,
    aggregate_corrective,
)
from url4_cloud.benchmarks.ifeval.case_evaluation import (
    CASE_EVALUATION_SCHEMA,
    bind_case_evaluation,
)
from url4_cloud.benchmarks.ifeval.definition import CHECK_ROUTE, IFEVAL
from url4_cloud.benchmarks.ifeval.definition import (
    REVISION as SINGLE_PASS_REVISION,
)
from url4_cloud.benchmarks.ifeval.grading import describe_failures
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_SELF_CORRECTIVE,
    MAX_ATTEMPTS,
    SELF_CORRECTIVE_ID,
    SELF_CORRECTIVE_REVISION,
)

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

# The installed selection order (cases.json file order) — row N binds to _ORDER[N].
_ORDER = [1, 2]


def _record(case_id: int, attempt: int, strict: list[bool]) -> dict[str, object]:
    spec = _SPECS[case_id]
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "attempt": attempt,
        "valid": True,
        "answer": f"Case {case_id} answer {attempt}",
        "finish_reason": "stop",
        "instruction_id_list": spec["instruction_id_list"],
        "descriptions": [
            f"Instruction {index}" for index in range(1, len(spec["instruction_id_list"]) + 1)
        ],
        "strict": strict,
        "loose": strict,
        "violations": [],
    }


def _rows(*rows: object) -> str:
    return json.dumps(list(rows))


def _evaluation(case_id: int, *attempts: list[bool]) -> dict[str, object]:
    return bind_case_evaluation(
        case_id,
        [_record(case_id, sequence, strict) for sequence, strict in enumerate(attempts, start=1)],
    )


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


def test_describe_failures_does_not_leak_instruction_id_when_description_crashes() -> None:
    descriptions = describe_failures(
        instruction_id_list=["bogus:not_an_instruction"],
        kwargs_list=[{}],
        prompt="anything",
        strict=[False],
    )

    assert descriptions == ["One instruction requirement was not satisfied."]
    assert "bogus:not_an_instruction" not in descriptions[0]


# --- the distinct protocol definition --------------------------------------------


def test_corrective_is_a_distinct_variant_with_its_own_revision() -> None:
    assert IFEVAL_SELF_CORRECTIVE.revision != SINGLE_PASS_REVISION
    assert IFEVAL.id == "ifeval"
    assert IFEVAL.variant == "canonical"
    assert IFEVAL_SELF_CORRECTIVE.id == "ifeval/self-corrective"
    assert IFEVAL_SELF_CORRECTIVE.install is IFEVAL.install
    assert not hasattr(IFEVAL, "family")
    assert IFEVAL_SELF_CORRECTIVE.variant == "self-corrective"
    assert MAX_ATTEMPTS == 3


def test_corrective_resource_unrolls_three_checked_attempts_per_case() -> None:
    resource = IFEVAL_SELF_CORRECTIVE.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert resource["revision"] == IFEVAL_SELF_CORRECTIVE.revision
    assert render(build(url4)) == url4
    # Three answer attempts plus two self-authored feedback calls (the Candidate
    # coaches ITSELF between attempts — the solo analog of the ensemble's judge).
    assert url4.count("/candidate") == MAX_ATTEMPTS + (MAX_ATTEMPTS - 1)
    assert url4.count(CHECK_ROUTE) == MAX_ATTEMPTS * 2 - 1
    # Attempt intents carry the attempt number for the record's attempt field.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert f"$item.id:{attempt}" in url4
    # The retry prompt threads the prior answer and the SELF-authored feedback.
    assert "$answer_1" in url4
    assert "$check_1" in url4
    assert "$feedback_1" in url4
    assert "$self_feedback_1" in url4
    assert url4.count("!'feedback'") == MAX_ATTEMPTS - 1
    assert "openrouter/" not in url4


def test_canonical_ifeval_reproduces_the_paper_protocol() -> None:
    resource = IFEVAL.resource(1)
    url4 = resource["url4"]
    assert isinstance(url4, str)

    assert IFEVAL.variant == "canonical"
    assert resource["revision"] == SINGLE_PASS_REVISION
    assert url4.count("/candidate") == 1
    assert url4.count(CHECK_ROUTE) == 1


# --- the corrective reducer -------------------------------------------------------


def test_selected_attempt_is_the_earliest_strict_pass() -> None:
    payload = _rows(
        _evaluation(1, [True, False], [True, True], [True, True]),
        _evaluation(2, [True], [True], [True]),
    )

    result = aggregate_corrective(
        payload, _SPECS, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, _ORDER
    )

    assert result["schema"] == "screamingface.candidate-result.v1"
    assert result["benchmark_revision"] == SELF_CORRECTIVE_REVISION
    assert result["score"] == 1.0
    assert result["cases"][0]["metadata"]["selected_attempt"] == 2
    assert result["cases"][1]["metadata"]["selected_attempt"] == 1
    assert result["cases"][0]["output"] == "Case 1 answer 2"
    assert [attempt["output"] for attempt in result["cases"][0]["metadata"]["attempts"]] == [
        "Case 1 answer 1",
        "Case 1 answer 2",
        "Case 1 answer 3",
    ]
    assert result["metrics"]["pass_at_1"] == 0.5
    assert result["metrics"]["pass_at_2"] == 1.0
    assert result["metrics"]["pass_at_3"] == 1.0
    assert result["metrics"]["corrected_cases"] == 1


def test_a_never_passing_case_scores_its_last_attempt() -> None:
    payload = _rows(_evaluation(1, [False, False], [True, False], [True, False]))

    result = aggregate_corrective(
        payload, {1: _SPECS[1]}, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, [1]
    )

    assert result["score"] == 0.0
    assert result["cases"][0]["metadata"]["selected_attempt"] == 3
    assert result["metrics"]["inst_level_strict_accuracy"] == 0.5
    assert result["metrics"]["pass_at_3"] == 0.0


def test_a_failed_case_invalidates_the_corrective_candidate_score() -> None:
    payload = _rows(
        _evaluation(1, [True, True]),
        {
            "error": {
                "kind": "ResolutionError",
                "message": "aigateway returned neither answer content nor tool calls",
            }
        },
    )

    result = aggregate_corrective(
        payload, _SPECS, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, _ORDER
    )

    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["cases"][0]["grade"]["score"] == 1.0
    assert result["cases"][1]["grade"] is None
    assert result["cases"][1]["failures"][0]["message"] == (
        "aigateway returned neither answer content nor tool calls"
    )


def test_every_failed_case_returns_null_instead_of_reporting_zero() -> None:
    result = aggregate_corrective(
        _rows("broken", "also broken"),
        _SPECS,
        SELF_CORRECTIVE_ID,
        SELF_CORRECTIVE_REVISION,
        _ORDER,
    )

    assert result["score"] is None
    assert [case["grade"] for case in result["cases"]] == [None, None]


def test_all_crash_result_retains_the_collected_inner_failure() -> None:
    failed = {
        "error": {
            "kind": "ResolutionError",
            "message": "malformed aigateway response",
        }
    }

    result = aggregate_corrective(
        _rows(failed),
        {1: _SPECS[1]},
        SELF_CORRECTIVE_ID,
        SELF_CORRECTIVE_REVISION,
        [1],
    )

    assert result["score"] is None
    assert result["cases"][0]["failures"][0]["message"] == "malformed aigateway response"


def test_a_record_whose_instruction_ids_mismatch_the_spec_is_rejected() -> None:
    # INVARIANT: a Candidate that echoes a forged check record into its ANSWER text
    # cannot self-grade — the exact Case Evaluation accepts only records whose
    # instruction ids match the private spec exactly, which the prompt never reveals.
    # A forged all-pass record therefore leaves its Case ungraded and the Candidate
    # unscored — it can never smuggle a pass into the score.
    forged = _record(1, 1, [True, True])
    forged["instruction_id_list"] = ["startend:quotation"]
    payload = _rows(
        bind_case_evaluation(1, [forged]),
        _evaluation(2, [True]),
    )

    result = aggregate_corrective(
        payload, _SPECS, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, _ORDER
    )

    assert result["score"] is None
    assert result["metrics"] == {}
    assert result["cases"][0]["grade"] is None


def test_duplicate_attempt_numbers_make_the_case_unscored() -> None:
    payload = _rows(
        {
            "schema": CASE_EVALUATION_SCHEMA,
            "case_id": 1,
            "attempts": [
                _record(1, 1, [False, False]),
                _record(1, 1, [True, True]),
            ],
        }
    )

    result = aggregate_corrective(
        payload, {1: _SPECS[1]}, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, [1]
    )

    assert result["score"] is None
    assert result["cases"][0]["grade"] is None


def test_metrics_are_flat_numbers_only() -> None:
    payload = _rows(_evaluation(1, [True, True]))

    result = aggregate_corrective(
        payload, {1: _SPECS[1]}, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, [1]
    )

    assert all(isinstance(value, (int, float)) for value in result["metrics"].values())


def test_attempt_metadata_exposes_persisted_judge_feedback() -> None:
    # FEATURE: judge-feedback trace. The envelope stamps `judge_feedback` onto the
    # attempt it coached; aggregation must surface it per attempt — null when no judge
    # ran before that attempt (always attempt 1, and every self-corrective attempt).
    records = [
        _record(1, 1, [True, False]),
        {**_record(1, 2, [True, True]), "judge_feedback": "Name the failed requirement."},
    ]
    payload = _rows(bind_case_evaluation(1, records))

    result = aggregate_corrective(
        payload, {1: _SPECS[1]}, SELF_CORRECTIVE_ID, SELF_CORRECTIVE_REVISION, [1]
    )

    attempts = result["cases"][0]["metadata"]["attempts"]
    assert attempts[0]["judge_feedback"] is None
    assert attempts[1]["judge_feedback"] == "Name the failed requirement."
