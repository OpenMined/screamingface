"""The Fusion writer receives one readable question-and-panel message."""

from __future__ import annotations

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate


def test_fusion_compiles_the_question_and_ordered_member_answers_as_text() -> None:
    compiled = compile_candidate(
        sf.Fusion(
            [
                sf.Model("provider/left", name="left) $literal"),
                sf.Model("provider/right"),
            ],
            synthesizer="provider/writer",
        )
    )

    assert compiled.url4 is not None
    assert "payload={" not in compiled.url4
    assert "Question:\u2028$input\u2028\u2028Panel answers (one per model):" in compiled.url4
    assert (
        "=== Model 1 ($synthesis_1_member_1_name) ===\u2028$model_1\u2028\u2028"
        "=== Model 2 ($synthesis_1_member_2_name) ===\u2028$model_2"
    ) in compiled.url4
    assert "Produce the unified prose answer now." not in compiled.url4
    # Member labels are bound as values rather than spliced into URL4 syntax. This keeps an
    # arbitrary valid public name readable without letting `)` or `$` change the expression.
    assert "synthesis_1_member_1_name='left) $$literal'" in compiled.url4
    assert "synthesis_1_member_2_name='right'" in compiled.url4
