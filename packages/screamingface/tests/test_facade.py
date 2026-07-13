"""The public facade — the exact quickstart flow, end to end.

STORY: as a researcher, I open 00_quickstart, run every cell, and see a real
gain read-out. This test IS that notebook, headless.
"""

from __future__ import annotations

import screamingface as sf


def test_version():
    assert sf.__version__ == "0.1.0"


def test_public_surface_is_exported():
    for name in (
        "setup",
        "connect",
        "models",
        "Fusion",
        "Run",
        "mock_widgets",
        "session",
        "EngineBackend",
        "SimulatedBackend",
    ):
        assert name in sf.__all__, f"missing from __all__: {name}"
        assert hasattr(sf, name)


def test_quickstart_flow(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sf.mock_widgets(True)

    sf.connect("anthropic")  # step 1 (headless twin)
    ids = sf.models.list(max_price=20)  # step 2
    assert len(ids) >= 3

    fusion = sf.Fusion(
        "fusion",
        models=ids[:3],  # step 3
        reduce="majority_vote",
        judge=ids[0],
    )
    assert fusion.url.startswith("url4://fusion?models=")

    run = fusion.evaluate("gpqa", first=20, seed=0)  # step 4
    assert run.sample_size == 20

    # step 5 — the payoff: numbers exist and are consistent
    assert 0.0 <= run.score <= 100.0
    assert 0.0 <= run.baseline <= 100.0
    assert run.gain == round(run.score - run.baseline, 1)
