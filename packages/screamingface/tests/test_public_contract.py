from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from url4 import build, render

import screamingface as sf


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def test_public_surface_is_url4_engine_only() -> None:
    assert sf.__version__ == "0.2.0"
    assert "MajorityVote" in sf.__all__
    assert "Member" not in sf.__all__
    assert "ModelConfig" in sf.__all__
    assert "ModelReducer" in sf.__all__
    assert "Reducer" in sf.__all__
    assert "Synthesize" not in sf.__all__
    assert "EngineError" in sf.__all__
    assert "config" in sf.__all__
    assert "setup" not in sf.__all__
    assert "connect" not in sf.__all__
    assert "GatewayError" not in sf.__all__


def test_reducer_is_an_abstract_category_not_a_factory() -> None:
    reducer_type: Any = sf.Reducer
    with pytest.raises(TypeError, match="abstract"):
        reducer_type()


@pytest.mark.parametrize("value", [-1, math.inf, math.nan])
def test_model_price_filter_rejects_invalid_values(value: float) -> None:
    with pytest.raises(ValueError, match="max_price"):
        sf.models.list(max_price=value)


def test_recipe_and_representations_are_explicit_and_secret_free() -> None:
    ids = sf.models.list()
    fusion = sf.Fusion(
        "safe",
        ids[:3],
        reducer=sf.MajorityVote(tie_breaker=ids[0]),
    )

    assert render(build(fusion.url4)) == fusion.url4
    assert "sk-super-secret-value" not in fusion.url4
    assert fusion.url4 not in repr(fusion)
    assert "TIE BREAKER" in repr(fusion)
    assert "Tie breaker" in fusion._repr_html_()


def test_model_reducer_recipe_is_canonical_and_names_its_model() -> None:
    ids = sf.models.list()
    fusion = sf.Fusion(
        "synthesis",
        ids,
        reducer=sf.ModelReducer(
            model=ids[0],
            prompt="Synthesize these labeled answers: $panel_answers",
            params={"temperature": 0.2, "max_tokens": 512},
        ),
    )

    assert render(build(fusion.url4)) == fusion.url4
    assert "fusion_answer=" in fusion.url4
    assert "temperature=0.2&max_tokens=512" in fusion.url4
    assert "screamingface.fusion-result.v2" in fusion.url4
    assert "reducer_model" in fusion.url4
    assert "reducer model" in fusion._repr_html_()


def test_model_dictionaries_have_stable_names_separate_from_models() -> None:
    model = sf.models.list()[0]
    fusion = sf.Fusion(
        "sampled",
        models=[
            {
                "model": model,
                "name": "sample-1",
                "params": {"temperature": 0.7, "seed": 1},
            },
            {
                "model": model,
                "name": "sample-2",
                "params": {"temperature": 0.7, "seed": 2},
            },
        ],
    )

    assert fusion.model_ids == (model, model)
    assert fusion.models == (
        {
            "model": model,
            "name": "sample-1",
            "params": {"temperature": 0.7, "seed": 1},
        },
        {
            "model": model,
            "name": "sample-2",
            "params": {"temperature": 0.7, "seed": 2},
        },
    )
    assert "panel_1_id: 'sample-1'" in fusion.url4
    assert "panel_2_id: 'sample-2'" in fusion.url4
    assert "temperature=0.7&seed=1" in fusion.url4


def test_plain_model_id_is_shorthand_for_minimal_model_dictionary() -> None:
    ids = sf.models.list()[:2]

    shorthand = sf.Fusion("shorthand", ids)
    explicit = sf.Fusion("explicit", [{"model": model} for model in ids])

    assert shorthand.url4 == explicit.url4


def test_duplicate_string_models_receive_automatic_private_slot_ids() -> None:
    model = sf.models.list()[0]
    fusion = sf.Fusion("self-consistency", [model, model])

    assert f"panel_1_id: '{model}#1'" in fusion.url4
    assert f"panel_2_id: '{model}#2'" in fusion.url4


def test_fusion_loads_safe_legacy_yaml_into_new_reducer(tmp_path: Path) -> None:
    ids = sf.models.list()
    config = tmp_path / "fusion.yaml"
    config.write_text(
        "\n".join(
            [
                "name: yaml-trio",
                "models:",
                *(f"  - {model}" for model in ids[:3]),
                "reduce: majority_vote",
                f"tie_breaker: {ids[0]}",
            ]
        ),
        encoding="utf-8",
    )

    fusion = sf.Fusion.from_yaml(config)

    assert fusion.name == "yaml-trio"
    assert fusion.models == tuple(ids[:3])
    assert fusion.reducer == sf.MajorityVote(tie_breaker=ids[0])


def test_fusion_loads_model_dictionaries_and_typed_reducer_from_yaml(tmp_path: Path) -> None:
    ids = sf.models.list()
    config = tmp_path / "fusion.yaml"
    config.write_text(
        "\n".join(
            [
                "name: configured-yaml",
                "models:",
                f"  - {ids[0]}",
                f"  - model: {ids[1]}",
                "    name: sampled-gemini",
                "    prompt: Answer $question",
                "    params:",
                "      temperature: 0.7",
                "reducer:",
                "  kind: model",
                f"  model: {ids[2]}",
                "  prompt: Synthesize $panel_answers for $question",
                "  params:",
                "    temperature: 0.0",
            ]
        ),
        encoding="utf-8",
    )

    fusion = sf.Fusion.from_yaml(config)

    assert fusion.model_ids == (ids[0], ids[1])
    assert fusion.models == (
        ids[0],
        {
            "model": ids[1],
            "name": "sampled-gemini",
            "prompt": "Answer $question",
            "params": {"temperature": 0.7},
        },
    )
    assert fusion.reducer == sf.ModelReducer(
        model=ids[2],
        prompt="Synthesize $panel_answers for $question",
        params={"temperature": 0.0},
    )
    assert "panel_2_id: 'sampled-gemini'" in fusion.url4
    assert "temperature=0.7" in fusion.url4
    assert sf.Fusion("rebuilt", fusion.models, reducer=fusion.reducer).url4 == fusion.url4


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("- not\n- a mapping\n", "mapping"),
        ("name: incomplete\n", "missing required"),
        ("name: bad\nmodels: [a, b]\nextra: true\n", "unknown field"),
        ("name: [bad]\nmodels: [a, b]\n", "'name' must be a string"),
        ("name: bad\nmodels: not-a-list\n", "'models' must be a list"),
        ("name: bad\nmodels: [a, b]\nreduce: [bad]\n", "'reduce' must be a string"),
        ("name: bad\nmodels: [a, b]\ntie_breaker: [bad]\n", "'tie_breaker' must be"),
        ("name: bad\nmodels: [a, b]\nreducer: majority_vote\n", "must be a mapping"),
        ("name: bad\nmodels: [a, b]\nreducer: {}\n", "missing required field: kind"),
        (
            "name: bad\nmodels: [a, b]\nreducer: {kind: other}\n",
            "unknown reducer kind",
        ),
        (
            "name: bad\nmodels: [a, b]\nreducer: {kind: majority_vote}\nreduce: majority_vote\n",
            "cannot combine",
        ),
        ("[unterminated\n", "invalid fusion YAML"),
    ],
)
def test_fusion_yaml_rejects_invalid_documents(tmp_path: Path, contents: str, message: str) -> None:
    config = tmp_path / "invalid.yaml"
    config.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        sf.Fusion.from_yaml(config)


def test_fusion_yaml_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="could not read fusion YAML"):
        sf.Fusion.from_yaml(tmp_path / "missing.yaml")
