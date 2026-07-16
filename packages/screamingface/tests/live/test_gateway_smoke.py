"""Opt-in provider smoke test for a running, already-authenticated AI Gateway."""

from __future__ import annotations

import os

import pytest

import screamingface as sf
import screamingface.evaluation as evaluation
from screamingface.data import Question

pytestmark = pytest.mark.skipif(
    os.getenv("SCREAMINGFACE_LIVE_TEST") != "1",
    reason="set SCREAMINGFACE_LIVE_TEST=1 to authorize the live provider smoke test",
)


@pytest.mark.live
def test_two_provider_gateway_path(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = os.environ["SCREAMINGFACE_GATEWAY_URL"]
    token = os.environ["SCREAMINGFACE_GATEWAY_TOKEN"]
    session = sf.setup(gateway=gateway, token=token)
    model_ids = sf.models.list(max_price=20)
    providers = {model_id.split("/", 1)[0] for model_id in model_ids}
    if len(providers) < 2:
        pytest.fail("Live smoke test requires active models from at least two providers")

    selected = [
        next(model_id for model_id in model_ids if model_id.startswith(f"{provider}/"))
        for provider in sorted(providers)[:2]
    ]
    questions = (
        Question(
            "transport-smoke-1",
            "science",
            "Which symbol denotes oxygen?",
            ("O", "N", "C", "H"),
            0,
        ),
    )
    monkeypatch.setattr(evaluation, "load_live_questions", lambda _first, _seed: questions)

    run = sf.Fusion("live-smoke", selected, judge=selected[0]).evaluate("gpqa", first=1)

    assert session.mode == "live"
    assert run.mode == "live"
    assert run.sample_size == 1
    assert run.cost_usd >= 0
