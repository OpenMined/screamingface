"""Member-machinery hardening for the LANL ensemble: judge-letter parsing and bounds.

The flow-level decision table (gates, early exit, Best-of-N) is pinned by
`test_ifeval_lanl_ensemble.py`; this file pins the parts a sloppy judge reply or a
malformed member payload could corrupt — the letter parser and the member-count
bounds — plus the URL4 prose-safety invariant.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4 import RelExpr, Text, expr, render, src, text
from url4.peer.server import Url4Node
from url4_cloud.benchmarks import install_benchmarks
from url4_cloud.benchmarks.contract import decode_candidate_invocation
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    LANL_SELECT_ROUTE,
    MAX_MEMBERS,
    MIN_MEMBERS,
    PROSE_CONSTANTS,
)


def _assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Describe tea without commas."}]', encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1,
                "prompt": "Describe tea without commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


def _members(*values: tuple[str, str]) -> list[dict[str, str]]:
    return [
        {
            "key": chr(65 + index),
            "name": f"member-{index + 1}",
            "kind": "model",
            "expression": f"/provider/member-{index + 1}",
            "answer": answer,
            "finish_reason": "stop",
            "feedback": feedback,
        }
        for index, (answer, feedback) in enumerate(values)
    ]


async def _select(tmp_path: Path, members: list[dict[str, str]], pick: str) -> str:
    """Call the LANL select with a never-pass round tied on satisfaction, so the
    judge's letter (or its rejection) is the only thing deciding the outcome."""

    _assets(tmp_path / "ifeval")
    node = Url4Node("test")
    install_benchmarks(node, tmp_path)
    payload = {"round": members, "tie": [pick]}
    result = await node.evaluate(
        render(
            expr(
                src(
                    text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
                    name="payload",
                    weight=0.0,
                ),
                RelExpr(path=LANL_SELECT_ROUTE, context="$payload", intent=Text("1:1")),
                intent=Text(""),
            )
        )
    )
    output, finish_reason = decode_candidate_invocation(result.text)
    assert finish_reason == "stop"
    return output


# Both answers satisfy no_comma equally (satisfaction 1.0 each) but neither carries the
# checker's PASSED verdict, so selection lands in the exact-tie branch where only the
# judge's letter (if unambiguous) decides.
_TIED = (("alpha", "failed"), ("beta", "failed"))


@pytest.mark.asyncio
async def test_a_prose_judge_reply_gets_no_vote(tmp_path: Path) -> None:
    # INVARIANT: only an unambiguous letter counts. Scanning prose would turn
    # "Based on the constraints..." into a pick of B via the first word.
    selected = await _select(
        tmp_path, _members(*_TIED), "Based on the constraints I would choose b"
    )
    assert selected == "alpha"


@pytest.mark.asyncio
async def test_a_punctuated_single_letter_reply_still_counts(tmp_path: Path) -> None:
    selected = await _select(tmp_path, _members(*_TIED), "(b)")
    assert selected == "beta"


@pytest.mark.asyncio
async def test_a_letter_outside_the_member_set_falls_back_to_the_first(
    tmp_path: Path,
) -> None:
    selected = await _select(tmp_path, _members(*_TIED), "zzz")
    assert selected == "alpha"


@pytest.mark.asyncio
async def test_selection_rejects_member_counts_outside_bounds(tmp_path: Path) -> None:
    with pytest.raises(Exception, match=f"{MIN_MEMBERS}..{MAX_MEMBERS} member answers"):
        await _select(tmp_path, _members(("alpha", "failed")), "A")


def test_prose_constants_stay_quote_and_comma_free() -> None:
    # INVARIANT: URL4 context prose ships unescaped — a quote corrupts the rendered
    # expression's re-parse and a top-level comma splits the context into slots
    # (edge_probe5, 2026-08-03). The exam's fixed prose must never contain either.
    for prose in PROSE_CONSTANTS:
        assert "'" not in prose
        assert "," not in prose
