"""Download the pinned IFEval dataset and emit its private runtime assets.

Run at IMAGE BUILD time, never at run time: a Job's rootfs is read-only apart from `/tmp`
and it has no network egress, so every benchmark artifact must exist before the Job starts.

    uv run --with datasets python -m url4_cloud.benchmarks.ifeval.prepare \
        --out /opt/benchmarks/ifeval [--limit 5]

Emits::

    <out>/cases.json              [{"id": …, "input": …}]  — the ONLY thing a client sees
    <out>/instructions/<id>.json  {key, prompt, instruction_id_list, kwargs} — private,
                                  read by `runtime.py` (check) and `aggregate.py`
    <out>/nltk_data/              punkt + punkt_tab tokenizers — offline corpus for the
                                  vendored verifier (never downloaded at run time)

INVARIANT — `cases.json` carries NO instruction ids or kwargs. The client receives case
ids and prompts while the machine-checkable constraints stay in the image, so a Candidate
cannot be tuned against the answer key.

Dataset: HF `google/IFEval` (arXiv:2311.07911), 541 rows, single `train` split. Fields:
``key / prompt / instruction_id_list / kwargs`` with kwargs positionally parallel to the
instruction ids.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.benchmarks.ifeval.definition import (
    CASE_COUNT,
    DATASET,
    DATASET_REVISION,
    INSTRUCTION_COUNT,
)

_HF_KEY_2785_PROMPT = (
    "What is inside Shinto shrines? Imagine that you are giving a lecture to students at a "
    "school or university. Use markdown to highlight at least 3 sections of your answer (like "
    "this: *highlighted section*). Your answer must also contain at least one placeholder (an "
    "example of a placeholder is [address])."
)
_OFFICIAL_KEY_2785_PROMPT = _HF_KEY_2785_PROMPT.replace(
    "at least one placeholder", "at least 3 placeholders"
)


class PrepareError(RuntimeError):
    """The dataset could not be turned into a declared world."""


def load_rows(limit: int | None = None) -> list[dict[str, Any]]:
    """Download the pinned dataset and return its rows.

    `datasets` is NOT a dependency of url4-cloud — this module runs at image BUILD time on
    a machine that has it; the Job that serves the artifacts needs only the emitted files.
    """

    try:
        datasets_mod = importlib.import_module("datasets")
    except ModuleNotFoundError as exc:
        raise PrepareError(
            "the `datasets` package is required to prepare a benchmark — "
            "`uv pip install datasets` in the build environment"
        ) from exc

    loaded = datasets_mod.load_dataset(DATASET, revision=DATASET_REVISION)
    rows: list[dict[str, Any]] = []
    for split in loaded:  # IFEval ships a single `train` split; iterate for uniformity
        for row in loaded[split]:
            rows.append(dict(row))
            if limit is not None and len(rows) >= limit:
                return rows
    return rows


def strip_nulls(kwargs_list: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Drop None-valued kwargs keys.

    WHY: a raw `datasets` load pads every kwargs dict with all-None keys for schema
    uniformity; passing a None through ``build_description`` would override a checker's
    real default and crash or, worse, silently change the constraint.
    """

    return [
        {key: value for key, value in kwargs.items() if value is not None} for kwargs in kwargs_list
    ]


def build(
    rows: Sequence[dict[str, Any]],
    out: Path,
    *,
    expected_count: int | None = None,
    expected_instruction_count: int | None = None,
) -> dict[str, Any]:
    """Write the public cases and private instruction specs read by IFEval's runtime."""

    if expected_count is not None and len(rows) != expected_count:
        raise PrepareError(
            f"expected {expected_count} IFEval cases, but the pinned dataset produced {len(rows)}"
        )
    instructions_dir = out / "instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)

    cases: list[dict[str, Any]] = []
    seen_case_ids: set[int] = set()
    instruction_count = 0
    for row in rows:
        case_id, spec = _prepared_case(row)
        if case_id in seen_case_ids:
            raise PrepareError(f"duplicate official IFEval key {case_id}")
        seen_case_ids.add(case_id)
        instruction_count += len(spec["instruction_id_list"])
        (instructions_dir / f"{case_id}.json").write_text(json.dumps(spec), encoding="utf-8")
        cases.append({"id": case_id, "input": spec["prompt"]})

    if expected_instruction_count is not None and instruction_count != expected_instruction_count:
        raise PrepareError(
            f"expected {expected_instruction_count} IFEval instructions, but the pinned dataset "
            f"produced {instruction_count}"
        )

    (out / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    return {"cases": len(cases), "instructions": instruction_count, "out": str(out)}


def _case_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PrepareError("every IFEval row must carry its positive official integer key")
    return value


def _prepared_case(row: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    case_id = _case_id(row.get("key"))
    prompt = _official_prompt(case_id, row.get("prompt"))
    if not prompt:
        raise PrepareError(f"case {case_id}: empty 'prompt' column")
    instruction_ids = row.get("instruction_id_list")
    kwargs_list = row.get("kwargs")
    if not isinstance(instruction_ids, list) or not instruction_ids:
        raise PrepareError(f"case {case_id}: empty instruction_id_list")
    if not isinstance(kwargs_list, list) or len(kwargs_list) != len(instruction_ids):
        raise PrepareError(
            f"case {case_id}: kwargs must be positionally parallel to instruction_id_list"
        )
    return case_id, {
        "key": case_id,
        "prompt": prompt,
        "instruction_id_list": instruction_ids,
        "kwargs": strip_nulls(kwargs_list),
    }


def _official_prompt(case_id: int, value: object) -> str:
    if not isinstance(value, str):
        raise PrepareError(f"case {case_id}: empty 'prompt' column")
    if case_id != 2785:
        return value
    if value == _OFFICIAL_KEY_2785_PROMPT:
        return value
    if value != _HF_KEY_2785_PROMPT:
        raise PrepareError("case 2785 no longer matches either pinned source wording")
    return _OFFICIAL_KEY_2785_PROMPT


def prepare_nltk(out: Path) -> dict[str, Any]:
    """Download the tokenizer corpus the vendored verifier reads, into the assets dir.

    Build-time network use is deliberate — the run-time Job reads this directory via
    ``grading.configure_nltk`` and never downloads.
    """

    import nltk

    from url4_cloud.benchmarks.ifeval.grading import configure_nltk

    target = out / "nltk_data"
    target.mkdir(parents=True, exist_ok=True)
    # WHY: nltk>=3.10's downloader rejects any target not registered in nltk.data.path
    # ("Security Violation: Unauthorized path"), so the directory is authorized first —
    # the same registration the run-time reader uses.
    configure_nltk(target)
    for resource in ("punkt", "punkt_tab"):
        if not nltk.download(resource, quiet=True, download_dir=str(target)):
            raise PrepareError(f"could not download the nltk resource {resource!r}")
    return {"nltk_data": str(target)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ifeval-prepare", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/opt/benchmarks/ifeval"))
    parser.add_argument("--limit", type=int, default=None, help="cap the case count (probes)")
    args = parser.parse_args(argv)

    try:
        rows = load_rows(args.limit)
        summary = build(
            rows,
            args.out,
            expected_count=CASE_COUNT if args.limit is None else args.limit,
            expected_instruction_count=INSTRUCTION_COUNT if args.limit is None else None,
        )
        summary |= prepare_nltk(args.out)
        from url4_cloud.benchmarks.ifeval.parity import verify_prepared_assets

        summary |= verify_prepared_assets(args.out)
    except (PrepareError, ValueError) as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())
