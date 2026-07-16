from __future__ import annotations

import math
from pathlib import Path

import pytest
from url4 import Expression, build, render

import screamingface as sf
import screamingface.session as session_module


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def test_mock_quickstart_contract_runs_end_to_end() -> None:
    session = sf.setup(mode="mock", static_widgets=True)

    assert session.mode == "mock"
    assert session.static_widgets is True
    assert session.dataset_source == "synthetic-gpqa-shaped"

    ids = sf.models.list(max_price=20)
    assert len(ids) >= 3

    fusion = sf.Fusion(
        "fusion",
        models=ids[:3],
        reduce="majority_vote",
        judge=ids[0],
    )

    assert render(build(fusion.url)) == fusion.url

    run = fusion.evaluate("gpqa", first=20, seed=0)
    assert run.mode == "mock"
    assert run.benchmark == "GPQA-shaped synthetic science fixture"
    assert run.dataset_source == "synthetic-gpqa-shaped"
    assert run.sample_size == 20
    assert run.gain == pytest.approx(run.score - run.baseline)
    assert run.gain > 0
    assert run.cost_usd == 0
    html = run._repr_html_()
    assert "MOCK · NO PROVIDER CLAIM" in html
    assert "frontier-trio" not in html
    assert "fusion" in html
    assert "PER-MODEL ACCURACY" in html
    assert "no provider spend" in html
    assert "reduce majority_vote" in html
    assert len(run.model_results) == 3


def test_url4_recipe_carries_versioned_import_metadata() -> None:
    sf.setup(mode="mock")
    ids = sf.models.list()
    fusion = sf.Fusion("Importable Fusion", ids[:3], judge=ids[0])

    parsed = build(fusion.url4)

    assert isinstance(parsed, Expression)
    assert render(parsed) == fusion.url4
    assert parsed.params == (
        ("sf_version", "1"),
        ("sf_name", "importable-fusion"),
        ("sf_judge", ids[0]),
    )


def test_setup_defaults_to_live_and_never_silently_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCREAMINGFACE_GATEWAY_URL", raising=False)
    monkeypatch.delenv("SCREAMINGFACE_GATEWAY_TOKEN", raising=False)
    monkeypatch.setattr(session_module, "_LOCAL_GATEWAY", "http://127.0.0.1:1")

    with pytest.raises(sf.GatewayUnavailable):
        sf.setup()

    assert sf.current_session() is None


@pytest.mark.parametrize("value", [-1, math.inf, math.nan])
def test_model_price_filter_rejects_invalid_values(value: float) -> None:
    sf.setup(mode="mock")

    with pytest.raises(ValueError, match="max_price"):
        sf.models.list(max_price=value)


def test_fusion_requires_member_judge() -> None:
    sf.setup(mode="mock")
    ids = sf.models.list()

    with pytest.raises(ValueError, match="judge"):
        sf.Fusion("bad", models=ids[:2], judge=ids[2])


def test_recipe_and_representations_do_not_contain_secrets() -> None:
    sf.setup(mode="mock")
    ids = sf.models.list()
    fusion = sf.Fusion("safe", models=ids[:2], judge=ids[0])
    secret = "sk-super-secret-value"

    assert secret not in fusion.url
    assert secret not in repr(fusion)


def test_mock_evaluation_is_deterministic() -> None:
    sf.setup(mode="mock")
    ids = sf.models.list(max_price=20)
    fusion = sf.Fusion("repeatable", models=ids[:3], judge=ids[0])

    first = fusion.evaluate("gpqa", first=20, seed=7)
    second = fusion.evaluate("gpqa", first=20, seed=7)

    assert first == second


def test_fusion_loads_safe_yaml_and_exposes_url4_on_request(tmp_path: Path) -> None:
    sf.setup(mode="mock")
    ids = sf.models.list()
    config = tmp_path / "fusion.yaml"
    config.write_text(
        "\n".join(
            [
                "name: yaml-trio",
                "models:",
                *(f"  - {model}" for model in ids[:3]),
                "reduce: majority_vote",
                f"judge: {ids[0]}",
            ]
        ),
        encoding="utf-8",
    )

    fusion = sf.Fusion.from_yaml(config)

    assert fusion.name == "yaml-trio"
    assert fusion.models == tuple(ids[:3])
    assert fusion.url4 == fusion.url
    assert fusion.url4 not in repr(fusion)
    assert "MODEL" in repr(fusion)
    assert "JUDGE" in repr(fusion)
    assert "<table" in fusion._repr_html_()
    assert fusion.url4 not in fusion._repr_html_()


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("- not\n- a mapping\n", "mapping"),
        ("name: incomplete\n", "missing required"),
        ("name: bad\nmodels: [a, b]\nextra: true\n", "unknown field"),
        ("name: [bad]\nmodels: [a, b]\n", "'name' must be a string"),
        ("name: bad\nmodels: not-a-list\n", "'models' must be a list"),
        ("name: bad\nmodels: [a, b]\nreduce: [bad]\n", "'reduce' must be a string"),
        ("name: bad\nmodels: [a, b]\njudge: [bad]\n", "'judge' must be a model ID"),
        ("[unterminated\n", "invalid fusion YAML"),
    ],
)
def test_fusion_yaml_rejects_invalid_documents(tmp_path: Path, contents: str, message: str) -> None:
    sf.setup(mode="mock")
    config = tmp_path / "invalid.yaml"
    config.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        sf.Fusion.from_yaml(config)


def test_fusion_yaml_reports_unreadable_file(tmp_path: Path) -> None:
    sf.setup(mode="mock")

    with pytest.raises(ValueError, match="could not read fusion YAML"):
        sf.Fusion.from_yaml(tmp_path / "missing.yaml")
