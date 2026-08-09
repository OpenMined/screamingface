from __future__ import annotations

import pytest
from url4 import expr, render, src, text

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate


def _url4(recipe: sf.Recipe) -> sf.Url4:
    value = compile_candidate(recipe).url4
    assert value is not None
    return sf.Url4(value)


def _linked_url4(recipe: sf.Recipe) -> sf.Url4:
    candidate = _url4(recipe)
    return sf.Url4(
        render(
            expr(
                src(text(candidate), name="candidate", weight=0.0),
                src(
                    "/benchmarks/draco/smoke/revision-1/cases",
                    name="rows",
                    weight=0.0,
                ),
                intent=text("$rows"),
            )
        )
    )


def test_url4_is_a_string_compatible_immutable_value() -> None:
    value = _url4(sf.Model("provider/model"))

    assert isinstance(value, str)
    assert str(value) == value
    assert value.startswith("(model_1:")


def test_model_url4_produces_editable_python() -> None:
    value = _url4(
        sf.Model(
            "provider/model",
            prompt="Cost is $5\nExplain it.",
            params={"temperature": 0.2, "seed": 1},
        )
    )

    assert (
        value.to_python()
        == """import screamingface as sf

candidate = sf.Model(
    'provider/model',
    prompt='Cost is $5\\nExplain it.',
    params={'temperature': 0.2, 'seed': 1},
)"""
    )


def test_fusion_url4_recovers_editable_topology_names_and_policy() -> None:
    value = _url4(
        sf.Fusion(
            [
                sf.Model("provider/a", name="left", prompt="Answer A"),
                sf.Model("provider/b", name="right"),
            ],
            name="panel",
            synthesizer="provider/synthesizer",
            prompt="Blend the answers",
            params={"temperature": 0.1},
        )
    )

    python = value.to_python()

    assert "candidate = sf.Fusion(" in python
    assert "'provider/a'" in python
    assert "name='left'" in python
    assert "prompt='Answer A'" in python
    assert "'provider/b'" in python
    assert "name='right'" in python
    assert "synthesizer='provider/synthesizer'" in python
    assert "prompt='Blend the answers'" in python
    assert "params={'temperature': 0.1}" in python
    assert "web_search" not in python


def test_linked_evaluation_url4_adds_the_editable_benchmark_call() -> None:
    value = _linked_url4(sf.Model("provider/model"))

    assert value.to_python().endswith(
        """report = sf.evaluate(
    candidate,
    benchmark='draco/smoke',
)"""
    )


def test_url4_to_python_rejects_generic_non_candidate_expressions() -> None:
    with pytest.raises(ValueError, match="compiled ScreamingFace model calls"):
        sf.Url4("(@)!'hello'").to_python()
