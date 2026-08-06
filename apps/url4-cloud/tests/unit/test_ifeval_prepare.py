"""IFEval asset preparation — pinned dataset rows into the private runtime layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.ifeval.prepare import PrepareError, build, prepare_nltk, strip_nulls

_HF_KEY_2785_PROMPT = (
    "What is inside Shinto shrines? Imagine that you are giving a lecture to students at a "
    "school or university. Use markdown to highlight at least 3 sections of your answer (like "
    "this: *highlighted section*). Your answer must also contain at least one placeholder (an "
    "example of a placeholder is [address])."
)


def _row(key: int, prompt: str) -> dict[str, object]:
    return {
        "key": key,
        "prompt": prompt,
        "instruction_id_list": ["punctuation:no_comma"],
        "kwargs": [{}],
    }


def test_strip_nulls_removes_only_none_valued_kwargs() -> None:
    # WHY: a raw HF `datasets` load pads every kwargs dict with all-None keys; passing a
    # None through build_description would crash a checker whose default is a real value.
    stripped = strip_nulls(
        [
            {"num_words": None, "relation": "at least"},
            {"num_highlights": 2, "section_spliter": None},
            {},
        ]
    )

    assert stripped == [{"relation": "at least"}, {"num_highlights": 2}, {}]


def test_build_emits_public_cases_and_private_instruction_specs(tmp_path: Path) -> None:
    rows = [_row(1000, "Write without commas."), _row(1001, "Also no commas here.")]

    summary = build(rows, tmp_path, expected_count=2)

    cases = json.loads((tmp_path / "cases.json").read_text(encoding="utf-8"))
    assert cases == [
        {"id": 1000, "input": "Write without commas."},
        {"id": 1001, "input": "Also no commas here."},
    ]
    # INVARIANT: cases.json carries NO instruction ids or kwargs. The client sees only the
    # prompt; the machine-checkable constraints stay in the image so a Candidate cannot be
    # tuned against the answer key.
    assert "instruction_id_list" not in json.dumps(cases)
    spec = json.loads((tmp_path / "instructions" / "1000.json").read_text(encoding="utf-8"))
    assert spec["prompt"] == "Write without commas."
    assert spec["instruction_id_list"] == ["punctuation:no_comma"]
    assert spec["kwargs"] == [{}]
    assert summary == {"cases": 2, "instructions": 2, "out": str(tmp_path)}


def test_build_preserves_positional_parallelism(tmp_path: Path) -> None:
    row = {
        "key": 1002,
        "prompt": "Two constraints.",
        "instruction_id_list": [
            "punctuation:no_comma",
            "length_constraints:number_words",
        ],
        "kwargs": [{}, {"relation": "at least", "num_words": 300, "unused": None}],
    }

    build([row], tmp_path, expected_count=1)

    spec = json.loads((tmp_path / "instructions" / "1002.json").read_text(encoding="utf-8"))
    assert len(spec["instruction_id_list"]) == len(spec["kwargs"])
    assert spec["kwargs"][1] == {"relation": "at least", "num_words": 300}


def test_build_rejects_a_count_mismatch(tmp_path: Path) -> None:
    with pytest.raises(PrepareError):
        build([_row(1000, "One row.")], tmp_path, expected_count=541)


def test_build_rejects_an_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(PrepareError):
        build([_row(1000, "")], tmp_path, expected_count=1)


def test_prepare_nltk_authorizes_the_target_before_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # INVARIANT: nltk>=3.10 rejects download targets not registered in nltk.data.path
    # ("Security Violation: Unauthorized path") — the target must be authorized first,
    # or every fresh image build fails.
    import nltk

    downloads: list[str] = []

    def fake_download(resource: str, *, quiet: bool, download_dir: str) -> bool:
        downloads.append(resource)
        return str(tmp_path / "nltk_data") in nltk.data.path

    monkeypatch.setattr(nltk, "download", fake_download)

    summary = prepare_nltk(tmp_path)

    assert downloads == ["punkt", "punkt_tab"]
    assert summary == {"nltk_data": str(tmp_path / "nltk_data")}


def test_build_rejects_skewed_instruction_kwargs_lengths(tmp_path: Path) -> None:
    row = {
        "key": 1003,
        "prompt": "Skewed.",
        "instruction_id_list": ["punctuation:no_comma"],
        "kwargs": [],
    }

    with pytest.raises(PrepareError):
        build([row], tmp_path, expected_count=1)


def test_build_preserves_official_keys_and_repairs_the_one_divergent_prompt(
    tmp_path: Path,
) -> None:
    row = {
        "key": 2785,
        "prompt": _HF_KEY_2785_PROMPT,
        "instruction_id_list": [
            "detectable_format:number_highlighted_sections",
            "detectable_content:number_placeholders",
        ],
        "kwargs": [{"num_highlights": 3}, {"num_placeholders": 3}],
    }

    build([row], tmp_path, expected_count=1, expected_instruction_count=2)

    cases = json.loads((tmp_path / "cases.json").read_text(encoding="utf-8"))
    spec = json.loads((tmp_path / "instructions" / "2785.json").read_text(encoding="utf-8"))
    assert cases[0]["id"] == 2785
    assert "at least 3 placeholders" in cases[0]["input"]
    assert spec["key"] == 2785
    assert spec["prompt"] == cases[0]["input"]


@pytest.mark.parametrize("key", [None, True, 0, -1, "1000"])
def test_build_rejects_noncanonical_case_keys(tmp_path: Path, key: object) -> None:
    row = _row(1000, "Prompt")
    row["key"] = key

    with pytest.raises(PrepareError, match="official integer key"):
        build([row], tmp_path, expected_count=1)


def test_build_rejects_duplicate_official_keys(tmp_path: Path) -> None:
    with pytest.raises(PrepareError, match="duplicate official IFEval key 1000"):
        build(
            [_row(1000, "First"), _row(1000, "Second")],
            tmp_path,
            expected_count=2,
        )
