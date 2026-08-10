"""Benchmarks own retrieval while Fusion synthesis is always retrieval-free."""

from __future__ import annotations

import pytest

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate


def test_compiled_fusion_members_inherit_benchmark_retrieval_but_synthesis_disables_it() -> None:
    """A Benchmark can enable retrieval without granting it to the Fusion writer."""

    compiled = compile_candidate(
        sf.Fusion(
            [sf.Model("provider/left"), sf.Model("provider/right")],
            synthesizer="provider/synthesizer",
        )
    )

    assert compiled.url4 is not None
    assert "/provider/left?max_tokens=4096&q=" in compiled.url4
    assert "/provider/right?max_tokens=4096&q=" in compiled.url4
    assert "/provider/synthesizer?max_tokens=4096&web_search=false" in compiled.url4
    assert compiled.url4.count("web_search=false") == 1
    assert compiled.synthesizer is not None
    assert "/provider/synthesizer?max_tokens=4096&web_search=false" in compiled.synthesizer.url4


@pytest.mark.parametrize("reserved", ["web_search", "plugins", "tools", "provider", "q"])
def test_execution_owned_parameters_are_rejected_on_every_candidate_type(reserved: str) -> None:
    with pytest.raises(ValueError, match=rf"{reserved!r} is reserved"):
        sf.Model("provider/model", params={reserved: True})

    with pytest.raises(ValueError, match=rf"{reserved!r} is reserved"):
        sf.Fusion(
            [sf.Model("provider/left"), sf.Model("provider/right")],
            synthesizer=sf.Model(
                "provider/synthesizer",
                params={reserved: True},
            ),
        )
