"""share — the flat url4:// recipe codec (emit only in v0.1).

AIDEV-NOTE: this flat format is INTERIM (spec §3) — OME-408 replaces it with
the real url4 expression grammar; only this module should know the format.
"""

from __future__ import annotations

from screamingface.fusion_core import FusionCore
from screamingface.share import to_url4


def test_emits_flat_recipe_with_short_ids():
    core = (FusionCore("my-fusion").add("an-1").add("dm-1")
            .reduce("majority_vote", judge="an-1"))
    assert to_url4(core) == (
        "url4://my-fusion?models=an-1+dm-1&reduce=majority_vote&loop=parallel&judge=an-1"
    )


def test_judge_omitted_when_unset():
    core = FusionCore("f").add("an-1").add("dm-1")
    assert "judge=" not in to_url4(core)
