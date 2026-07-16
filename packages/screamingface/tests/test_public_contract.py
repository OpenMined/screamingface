from __future__ import annotations

import math
from pathlib import Path

import pytest
from url4 import build, render

import screamingface as sf


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def test_public_surface_is_url4_engine_only() -> None:
    assert sf.__version__ == "0.2.0"
    assert "MajorityVote" in sf.__all__
    assert "EngineError" in sf.__all__
    assert "config" in sf.__all__
    assert "setup" not in sf.__all__
    assert "connect" not in sf.__all__
    assert "GatewayError" not in sf.__all__


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
