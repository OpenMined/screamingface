from __future__ import annotations

from typing import Any, cast

import pytest
from url4 import expr, render, src, text

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface.url4 import _Call, _params, _render_recipe


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


def _embedded_url4(candidate: str) -> sf.Url4:
    return sf.Url4(
        render(
            expr(
                src(text(candidate), name="candidate", weight=0.0),
                intent=text("$candidate"),
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


def test_url4_value_requires_nonblank_text() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        sf.Url4(cast(Any, 1))
    with pytest.raises(ValueError, match="non-empty string"):
        sf.Url4("  ")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("(", "must be valid URL4"),
        ("/provider/model", "compiled ScreamingFace model calls"),
        (_embedded_url4("("), "invalid embedded Candidate"),
        (_embedded_url4("/provider/model"), "compiled ScreamingFace model calls"),
    ],
)
def test_url4_to_python_rejects_malformed_candidate_shapes(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        sf.Url4(value).to_python()


def test_url4_to_python_rejects_an_unknown_result_binding() -> None:
    value = _url4(sf.Model("provider/model"))
    suffix = "!'$model_1'"
    assert value.endswith(suffix)
    invalid = sf.Url4(f"{value.removesuffix(suffix)}!'$model_2'")

    with pytest.raises(ValueError, match="unsupported result binding"):
        invalid.to_python()


def test_url4_to_python_preserves_boolean_model_parameters() -> None:
    value = _url4(
        sf.Model(
            "provider/model",
            params={"feature_enabled": True, "fallback_enabled": False},
        )
    )

    python = value.to_python()

    assert "'feature_enabled': True" in python
    assert "'fallback_enabled': False" in python


def test_linked_url4_without_a_benchmark_route_only_forks_the_candidate() -> None:
    value = _embedded_url4(_url4(sf.Model("provider/model")))

    python = value.to_python()

    assert "candidate = sf.Model(" in python
    assert "sf.evaluate(" not in python


def test_url4_conversion_rejects_invalid_internal_references_and_parameters() -> None:
    with pytest.raises(ValueError, match="unknown binding"):
        _render_recipe("model_2", {}, explicit_name=None, indent=0)

    incomplete_fusion = _Call(
        binding="synthesis_1",
        kind="fusion",
        model="provider/synthesizer",
        dependencies=("model_1",),
        member_names={},
        prompt="Blend",
        params=(),
    )
    with pytest.raises(ValueError, match="at least two Candidate members"):
        _render_recipe(
            "synthesis_1",
            {"synthesis_1": incomplete_fusion},
            explicit_name=None,
            indent=0,
        )

    with pytest.raises(ValueError, match="scalar values"):
        _params((("temperature", None),))
