from __future__ import annotations

import os

import pytest

from screamingface.data import load_live_questions

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("SCREAMINGFACE_GPQA_LIVE_TEST") != "1",
        reason="set SCREAMINGFACE_GPQA_LIVE_TEST=1 after accepting the gated GPQA terms",
    ),
]


def test_authorized_gpqa_diamond_loads_without_rendering_examples() -> None:
    questions = load_live_questions(1, seed=0)

    assert len(questions) == 1
    assert questions[0].id == "gpqa-diamond-0"
    assert len(questions[0].options) == 4
