"""Build-time parity proof against Google's pinned IFEval evaluation protocol."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from langdetect import DetectorFactory

from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.aggregate import load_cases, load_specs
from url4_cloud.benchmarks.ifeval.vendor import evaluation_lib

_FULL_PARITY_CASES = 541
_FULL_PARITY_SHA256 = "3d8ebd64456040380eb88b9ca5fd8566db4e93c53c75165a47552c8b57801f4b"


class ParityError(ValueError):
    """The shipped evaluator disagrees with Google's pinned protocol oracle."""


def verify_prepared_assets(root: Path) -> dict[str, Any]:
    """Compare every prepared Case's vectors and all four global metrics."""

    grading.configure_nltk(root / "nltk_data")
    cases = load_cases(root / "cases.json")
    specs = load_specs(root / "instructions")
    compared = [_compare_case(case, specs) for case in cases]
    official_vectors = [official for official, _shipped in compared]
    shipped_vectors = [shipped for _official, shipped in compared]
    official_metrics = _metrics(official_vectors)
    shipped_metrics = _metrics(shipped_vectors)
    _validate_metrics(official_metrics, shipped_metrics)
    digest = _vector_digest(official_vectors)
    _validate_full_digest(len(official_vectors), digest)
    return {
        "parity_cases": len(official_vectors),
        "parity_metrics": official_metrics,
        "parity_sha256": digest,
    }


def _compare_case(
    case: Mapping[str, object],
    specs: Mapping[int, Mapping[str, Any]],
) -> tuple[dict[str, object], dict[str, object]]:
    case_id = _case_id(case)
    spec = specs.get(case_id)
    if spec is None:
        raise ParityError(f"official Case {case_id} has no prepared instruction spec")
    response = _golden_response(case_id, spec["prompt"])
    official, shipped = _seeded_vectors(case_id, spec, response)
    shipped_record = {"case_id": case_id, **shipped}
    if shipped_record != official:
        raise ParityError(
            f"IFEval protocol mismatch for official Case {case_id}: "
            f"official={official}, shipped={shipped_record}"
        )
    return official, shipped_record


def _seeded_vectors(
    case_id: int,
    spec: Mapping[str, Any],
    response: str,
) -> tuple[dict[str, object], Mapping[str, object]]:
    random_state = random.getstate()
    detector_seed = DetectorFactory.seed
    try:
        random.seed(f"screamingface-ifeval-parity:{case_id}")
        DetectorFactory.seed = case_id
        official = _official_vectors(case_id, spec, response)
        random.seed(f"screamingface-ifeval-parity:{case_id}")
        DetectorFactory.seed = case_id
        shipped = grading.check_case(
            instruction_id_list=spec["instruction_id_list"],
            kwargs_list=spec["kwargs"],
            prompt=spec["prompt"],
            response=response,
        )
    finally:
        random.setstate(random_state)
        DetectorFactory.seed = detector_seed
    return official, shipped


def _validate_metrics(
    official: Mapping[str, float],
    shipped: Mapping[str, float],
) -> None:
    if shipped != official:
        raise ParityError(f"IFEval global metric mismatch: official={official}, shipped={shipped}")


def _vector_digest(vectors: Sequence[Mapping[str, object]]) -> str:
    canonical = json.dumps(vectors, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_full_digest(case_count: int, digest: str) -> None:
    if case_count == _FULL_PARITY_CASES and digest != _FULL_PARITY_SHA256:
        raise ParityError(
            f"full IFEval golden-vector digest changed: expected {_FULL_PARITY_SHA256}, "
            f"got {digest}"
        )


def _official_vectors(
    case_id: int,
    spec: Mapping[str, Any],
    response: str,
) -> dict[str, object]:
    example = evaluation_lib.InputExample(
        key=case_id,
        instruction_id_list=list(spec["instruction_id_list"]),
        prompt=spec["prompt"],
        kwargs=[dict(kwargs) for kwargs in spec["kwargs"]],
    )
    strict = evaluation_lib.test_instruction_following_strict(example, response)
    loose = evaluation_lib.test_instruction_following_loose(example, response)
    return {
        "case_id": case_id,
        "strict": strict.follow_instruction_list,
        "loose": loose.follow_instruction_list,
    }


def _golden_response(case_id: int, prompt: str) -> str:
    """Stable response corpus that exercises both passing and failing verifier paths."""

    responses = (
        prompt,
        f'"{prompt}"',
        f"Preface\n*{prompt}*\n- FIRST item\n- second item\n[address]\nP.S. Done",
        '{"answer":"YES","sections":["FIRST","SECOND","THIRD"]}',
        "YES\n\nFIRST SECOND THIRD\n\nNo comma appears here",
    )
    return responses[case_id % len(responses)]


def _metrics(vectors: Sequence[Mapping[str, object]]) -> dict[str, float]:
    strict = [_bool_vector(record.get("strict"), "strict") for record in vectors]
    loose = [_bool_vector(record.get("loose"), "loose") for record in vectors]
    return {
        "prompt_level_strict_accuracy": _mean([all(values) for values in strict]),
        "inst_level_strict_accuracy": _mean([value for values in strict for value in values]),
        "prompt_level_loose_accuracy": _mean([all(values) for values in loose]),
        "inst_level_loose_accuracy": _mean([value for values in loose for value in values]),
    }


def _mean(values: Sequence[object]) -> float:
    return sum(bool(value) for value in values) / len(values) if values else 0.0


def _bool_vector(value: object, label: str) -> list[bool]:
    if not isinstance(value, list) or not all(type(item) is bool for item in value):
        raise ParityError(f"official IFEval {label} result is not a boolean vector")
    return value


def _case_id(case: Mapping[str, object]) -> int:
    value = case.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ParityError("prepared IFEval Case has no positive official integer id")
    return value


__all__ = ["ParityError", "verify_prepared_assets"]
