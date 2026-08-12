from __future__ import annotations

from typing import Any, cast

import pytest
from url4 import RelExpr, expr, render, src, text

import screamingface as sf
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.url4 import _candidate_from_url4
from screamingface.url4 import _params


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


def test_every_complete_recipe_url4_has_one_canonical_recipe_descriptor() -> None:
    model = _url4(sf.Model("provider/model"))
    fusion = _url4(
        sf.Fusion(
            [sf.Model("provider/a"), sf.Model("provider/b")],
            synthesizer="provider/synthesizer",
        )
    )
    pipeline = _url4(sf.Pipeline([sf.Model("provider/draft"), sf.Model("provider/review")]))

    for value in (model, fusion, pipeline):
        assert value.count("_sf_recipe:") == 1
        assert "screamingface.recipe.v1" in value


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
            synthesizer=sf.Model(
                "provider/synthesizer",
                prompt="Blend the answers",
                params={"temperature": 0.1},
            ),
        )
    )

    python = value.to_python()

    assert "candidate = sf.Fusion(" in python
    assert "'provider/a'" in python
    assert "name='left'" in python
    assert "prompt='Answer A'" in python
    assert "'provider/b'" in python
    assert "name='right'" in python
    assert "synthesizer=sf.Model(" in python
    assert "        'provider/synthesizer'," in python
    assert "        prompt='Blend the answers'," in python
    assert "        params={'temperature': 0.1}," in python
    assert "web_search" not in python


def test_pipeline_url4_recovers_serial_and_nested_parallel_topology() -> None:
    value = _url4(
        sf.Pipeline(
            [
                sf.Model("provider/draft", name="draft"),
                sf.Fusion(
                    [sf.Model("provider/reviewer-a"), sf.Model("provider/reviewer-b")],
                    name="review-panel",
                    synthesizer="provider/reconciler",
                ),
                sf.Model("provider/final", prompt="Return only the final answer."),
            ],
            name="draft-review-final",
        )
    )

    python = value.to_python()

    assert "candidate = sf.Pipeline(" in python
    assert "name='draft-review-final'" in python
    assert "name='draft'" in python
    assert "        sf.Fusion(" in python
    assert "            name='review-panel'," in python
    assert "'provider/reconciler'" in python
    assert "prompt='Return only the final answer.'" in python
    assert python.index("'provider/draft'") < python.index("'provider/reviewer-a'")
    assert python.index("'provider/reconciler'") < python.index("'provider/final'")


def test_fusion_url4_recovers_a_pipeline_synthesizer() -> None:
    value = _url4(
        sf.Fusion(
            [sf.Model("provider/a"), sf.Model("provider/b")],
            synthesizer=sf.Pipeline(
                [
                    sf.Model("provider/judge", prompt="Choose one answer."),
                    sf.Model("provider/writer", prompt="Polish it."),
                ],
                name="judge-writer",
            ),
        )
    )

    python = value.to_python()

    assert "candidate = sf.Fusion(" in python
    assert "    synthesizer=sf.Pipeline(" in python
    assert "name='judge-writer'" in python
    assert "'provider/judge'" in python
    assert "'provider/writer'" in python


def test_pipeline_synthesizer_role_defaults_are_not_rendered_as_explicit_prompts() -> None:
    value = _url4(
        sf.Fusion(
            ["provider/a"],
            synthesizer=sf.Pipeline(["provider/judge", "provider/writer"]),
        )
    )

    python = value.to_python()

    assert "prompt=" not in python
    assert "params=" not in python


def test_linked_pipeline_url4_replay_preserves_kind_name_and_serial_dependencies() -> None:
    value = _linked_url4(
        sf.Pipeline(
            [sf.Model("provider/draft"), sf.Model("provider/review")],
            name="review-chain",
        )
    )

    candidate = _candidate_from_url4(value)

    assert candidate.kind == "pipeline"
    assert candidate.name == "review-chain"
    assert candidate.models == ("provider/draft", "provider/review")
    assert [operation.kind for operation in candidate.operations] == ["model", "model"]
    assert [operation.depends_on for operation in candidate.operations] == [
        (),
        ("op_model_1",),
    ]


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
    with pytest.raises(ValueError, match="scalar values"):
        _params((("temperature", None),))


def test_url4_conversion_rejects_topology_metadata_that_disagrees_with_the_calls() -> None:
    value = _url4(sf.Pipeline([sf.Model("provider/a"), sf.Model("provider/b")]))
    invalid = sf.Url4(value.replace('"binding":"model_2"', '"binding":"model_99"', 1))

    with pytest.raises(ValueError, match="invalid Pipeline topology metadata"):
        invalid.to_python()


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ("{", "invalid Recipe topology metadata"),
        (
            '{"schema":"screamingface.recipe.v2","recipe":{}}',
            "unsupported Recipe topology metadata",
        ),
        ('{"schema":"screamingface.recipe.v1"}', "invalid Recipe topology metadata"),
        (
            '{"schema":"screamingface.recipe.v1","recipe":[]}',
            "invalid Recipe topology metadata",
        ),
        (
            '{"schema":"screamingface.recipe.v1","recipe":'
            '{"binding":"model_1","kind":"unknown","name":"candidate"}}',
            "invalid Recipe topology metadata",
        ),
        (
            '{"schema":"screamingface.recipe.v1","recipe":'
            '{"binding":"model_1","kind":"model","name":"candidate",'
            '"named":false,"role":"grader"}}',
            "invalid Model topology metadata",
        ),
    ],
)
def test_url4_conversion_rejects_untrusted_topology_metadata(
    metadata: str,
    message: str,
) -> None:
    value = sf.Url4(
        render(
            expr(
                src(
                    RelExpr(path="/provider/model", context="$input", intent=text("Answer.")),
                    name="model_1",
                    weight=0.0,
                ),
                src(text(metadata), name="_sf_recipe", weight=0.0),
                intent=text("$model_1"),
            )
        )
    )

    with pytest.raises(ValueError, match=message):
        value.to_python()


def test_url4_conversion_requires_the_canonical_recipe_descriptor() -> None:
    value = sf.Url4(
        render(
            expr(
                src(
                    RelExpr(path="/provider/model", context="$input", intent=text("Answer.")),
                    name="model_1",
                    weight=0.0,
                ),
                intent=text("$model_1"),
            )
        )
    )

    with pytest.raises(ValueError, match="missing required Recipe metadata"):
        value.to_python()
