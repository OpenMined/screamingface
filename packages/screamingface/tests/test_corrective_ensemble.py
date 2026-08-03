"""The CorrectiveEnsemble recipe — check-and-retry as a candidate.

FEATURE: the Skurikhin et al. verifying ensemble compiled into one candidate blob.
STORY: as a researcher, my ensemble's drafts are graded by the benchmark's own
checker mid-flight, while the exam I publish against stays single-pass IFEval.
"""

from __future__ import annotations

from typing import cast

import pytest

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface.corrective import MAX_ATTEMPTS
from screamingface.errors import PlanningError

_ACTIONS = {
    "check": "/benchmarks/ifeval/rev/check",
    "select": "/benchmarks/ifeval/rev/select",
    "finalize": "/benchmarks/ifeval/rev/finalize",
}


def _ensemble() -> sf.CorrectiveEnsemble:
    return sf.CorrectiveEnsemble(
        [sf.Model("provider/a"), sf.Model("provider/b"), sf.Model("provider/c")],
        judge=sf.Model("provider/judge"),
    )


# --- the recipe value --------------------------------------------------------------


def test_the_recipe_infers_a_descriptive_name() -> None:
    assert _ensemble().name == "a+b+c (corrective)"


def test_members_must_be_two_to_four_models() -> None:
    with pytest.raises(ValueError):
        sf.CorrectiveEnsemble([sf.Model("provider/a")], judge=sf.Model("provider/j"))
    with pytest.raises(TypeError):
        wrong_members = [
            sf.Model("provider/a"),
            sf.Fusion([sf.Model("provider/b"), sf.Model("provider/c")]),
        ]
        # The wrong member type IS the subject — cast past the static check.
        sf.CorrectiveEnsemble(cast("list[sf.Model]", wrong_members), judge=sf.Model("provider/j"))


def test_the_judge_must_be_a_model() -> None:
    with pytest.raises(TypeError):
        sf.CorrectiveEnsemble(
            [sf.Model("provider/a"), sf.Model("provider/b")],
            judge="provider/j",  # type: ignore[arg-type]
        )


# --- compilation -------------------------------------------------------------------


def test_compiling_without_verifier_actions_raises_a_clear_planning_error() -> None:
    # INVARIANT: the recipe is inapplicable without a machine checker — the error
    # must say WHY and name the fix, because this is the first thing every new user
    # will hit when pointing the ensemble at draco.
    with pytest.raises(PlanningError) as caught:
        compile_candidate(_ensemble(), actions=None)

    assert "verifier benchmark" in str(caught.value)
    assert "ifeval" in str(caught.value)


def test_the_compiled_blob_is_the_bounded_corrective_loop() -> None:
    compiled = compile_candidate(_ensemble(), actions=_ACTIONS)

    assert compiled.kind == "corrective"
    assert compiled.models == ("provider/a", "provider/b", "provider/c", "provider/judge")
    url4 = compiled.url4
    # 3 members x 3 attempts answer nodes, checked and fed back individually.
    assert url4.count("/provider/a?") == MAX_ATTEMPTS
    assert url4.count("/provider/judge?") == MAX_ATTEMPTS
    # Per attempt: one check+feedback per member draft, plus one for the selection.
    assert url4.count(_ACTIONS["check"]) == MAX_ATTEMPTS * (2 * 3 + 2)
    assert url4.count(_ACTIONS["select"]) == MAX_ATTEMPTS
    assert url4.count(_ACTIONS["finalize"]) == 1
    # The checker is addressed per case via the engine-bound $case reference.
    assert "$case" in url4
    # INVARIANT: members see feedback TEXT only — the raw record reference flows into
    # engine routes exclusively, so no model context ever embeds a check record.
    assert "ce_chk_a_1" in url4
    assert url4.count("!'feedback'") == MAX_ATTEMPTS * (3 + 1)


def test_the_blob_only_needs_input_and_case_from_outside() -> None:
    compiled = compile_candidate(_ensemble(), actions=_ACTIONS)

    unresolved = {token for token in ("$input", "$case") if token not in compiled.url4}
    assert unresolved == set()
