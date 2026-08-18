"""The retrieval policy DRACO ships as one of its declared artifacts.

FEATURE: a benchmark image carries its own blocklist at its own url4 address, so benchmarks that
disagree about what to exclude share one set of model routes.
STORY: as a researcher I need the guard that stops a candidate reading its own answer key to
travel with the benchmark, and to be named in the expression so the score can be attributed.

INVARIANT: `rubrics/` stays undeclared. The policy is safe to address because it names PUBLIC
leak sources and carries no weight and no requirement text; the weighted rubric is neither.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from screamingface_engine.benchmarks.draco import prepare


def test_the_policy_is_written_as_an_addressable_artifact(tmp_path: Path) -> None:
    written = prepare.write_policy(tmp_path)

    document = json.loads(written.read_text(encoding="utf-8"))
    assert written == tmp_path / "policy" / "retrieval.json"
    assert document["id"] == prepare.RETRIEVAL_POLICY_ID
    assert document["excluded_domains"] == list(prepare.EXCLUDED_DOMAINS)


def test_the_policy_carries_the_draco_leak_sources(tmp_path: Path) -> None:
    """The dataset card, the reproduction post and the paper are where the answer key lives."""
    document = json.loads(prepare.write_policy(tmp_path).read_text(encoding="utf-8"))

    joined = " ".join(document["excluded_domains"])
    for source in ("huggingface.co", "openrouter.ai", "arxiv.org"):
        assert source in joined


def test_an_empty_policy_fails_the_BUILD(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """WHY here and not in the runner: the runner deliberately ACCEPTS an empty policy, because a
    benchmark may declare unrestricted retrieval as an explicit, attributable statement. For DRACO
    an empty list means the generator broke — and a generation bug belongs to the build, not to a
    run that would score high and look clean."""
    monkeypatch.setattr(prepare, "EXCLUDED_DOMAINS", ())

    with pytest.raises(prepare.PrepareError, match="policy is empty"):
        prepare.write_policy(tmp_path)
