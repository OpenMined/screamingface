"""Model routes fail as SDK planning errors before URL4 rendering or execution."""

from __future__ import annotations

import pytest

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate


def test_expression_path_incompatible_model_id_is_a_planning_error() -> None:
    model = sf.Model("huggingface/google/gemma-2-2b-it:featherless-ai")

    with pytest.raises(sf.PlanningError, match="cannot be addressed by this Engine") as caught:
        compile_candidate(model)

    assert caught.value.code == "invalid_model_route"
    assert caught.value.permanent is True
    assert caught.value.details == {"model": model.model}


def test_url4_expression_path_compatible_model_id_still_compiles() -> None:
    compiled = compile_candidate(sf.Model("openrouter/openai/gpt-5.5"))

    assert compiled.models == ("openrouter/openai/gpt-5.5",)
    assert "/openrouter/openai/gpt-5.5" in (compiled.url4 or "")
