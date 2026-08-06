"""Immutable, Benchmark-neutral Case Result values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from screamingface._immutable_json import freeze_json, freeze_mapping, thaw_json, thaw_mapping
from screamingface._report_primitives import Failure, _nonblank

type ProducerType = Literal["model", "deterministic"]


@dataclass(frozen=True, slots=True)
class EvidenceProducer:
    """The Engine-known producer of one observed grading result."""

    type: ProducerType
    id: str

    def __post_init__(self) -> None:
        if self.type not in {"model", "deterministic"}:
            raise ValueError("Evidence producer type must be 'model' or 'deterministic'")
        object.__setattr__(self, "id", _nonblank(self.id, "Evidence producer id"))

    def to_dict(self) -> dict[str, object]:
        return {"type": self.type, "id": self.id}


@dataclass(frozen=True, slots=True, init=False)
class Evidence:
    """One exact observation accepted or rejected by a grading Check."""

    sequence: int
    producer: EvidenceProducer
    valid: bool
    outcome: object | None
    explanation: str | None
    raw_output: object
    _metadata: Mapping[str, object] = field(repr=False)

    def __init__(
        self,
        *,
        sequence: int,
        producer: EvidenceProducer,
        valid: bool,
        raw_output: object,
        outcome: object | None = None,
        explanation: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("Evidence sequence must be a positive integer")
        if not isinstance(producer, EvidenceProducer):
            raise TypeError("Evidence producer must be an sf.EvidenceProducer")
        if not isinstance(valid, bool):
            raise TypeError("Evidence valid must be a boolean")
        if explanation is not None:
            explanation = _nonblank(explanation, "Evidence explanation")
        if not valid and (outcome is not None or explanation is not None):
            raise ValueError("invalid Evidence cannot contain an outcome or explanation")
        values = {
            "sequence": sequence,
            "producer": producer,
            "valid": valid,
            "outcome": freeze_json(outcome, "Evidence outcome"),
            "explanation": explanation,
            "raw_output": freeze_json(raw_output, "Evidence raw_output"),
            "_metadata": freeze_mapping(metadata or {}, "Evidence metadata"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def metadata(self) -> Mapping[str, object]:
        return self._metadata

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "sequence": self.sequence,
            "producer": self.producer.to_dict(),
            "valid": self.valid,
            "raw_output": thaw_json(self.raw_output),
            "metadata": thaw_mapping(self._metadata),
        }
        if self.outcome is not None:
            value["outcome"] = thaw_json(self.outcome)
        if self.explanation is not None:
            value["explanation"] = self.explanation
        return value


@dataclass(frozen=True, slots=True, init=False)
class Check:
    """One ordered Benchmark-owned grading check and all of its Evidence."""

    type: str
    id: str
    label: str
    evidence: tuple[Evidence, ...]
    outcome: object | None
    score: float | None
    _metadata: Mapping[str, object] = field(repr=False)

    def __init__(
        self,
        *,
        type: str,
        id: str,
        label: str,
        evidence: Sequence[Evidence],
        metadata: Mapping[str, object] | None = None,
        outcome: object | None = None,
        score: float | None = None,
    ) -> None:
        selected_evidence = tuple(evidence)
        if any(not isinstance(item, Evidence) for item in selected_evidence):
            raise TypeError("Check evidence must contain sf.Evidence values")
        sequences = [item.sequence for item in selected_evidence]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("Check Evidence sequences must be unique and ordered")
        values = {
            "type": _nonblank(type, "Check type"),
            "id": _nonblank(id, "Check id"),
            "label": _nonblank(label, "Check label"),
            "evidence": selected_evidence,
            "outcome": freeze_json(outcome, "Check outcome"),
            "score": _optional_number(score, "Check score"),
            "_metadata": freeze_mapping(metadata or {}, "Check metadata"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def metadata(self) -> Mapping[str, object]:
        return self._metadata

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "type": self.type,
            "id": self.id,
            "label": self.label,
            "evidence": [item.to_dict() for item in self.evidence],
            "metadata": thaw_mapping(self._metadata),
        }
        if self.outcome is not None:
            value["outcome"] = thaw_json(self.outcome)
        if self.score is not None:
            value["score"] = self.score
        return value


@dataclass(frozen=True, slots=True, init=False)
class CaseGrade:
    """One Benchmark-owned grade for a Case."""

    method: str
    score: float
    checks: tuple[Check, ...]
    _metrics: Mapping[str, object] = field(repr=False)

    def __init__(
        self,
        *,
        method: str,
        score: float,
        metrics: Mapping[str, object],
        checks: Sequence[Check],
    ) -> None:
        selected_checks = tuple(checks)
        if any(not isinstance(item, Check) for item in selected_checks):
            raise TypeError("Case Grade checks must contain sf.Check values")
        ids = [item.id for item in selected_checks]
        if len(ids) != len(set(ids)):
            raise ValueError("Case Grade Check ids must be unique")
        values = {
            "method": _nonblank(method, "Case Grade method"),
            "score": _required_number(score, "Case Grade score"),
            "checks": selected_checks,
            "_metrics": freeze_mapping(metrics, "Case Grade metrics"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def metrics(self) -> Mapping[str, object]:
        return self._metrics

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "score": self.score,
            "metrics": thaw_mapping(self._metrics),
            "checks": [item.to_dict() for item in self.checks],
        }


@dataclass(frozen=True, slots=True, init=False)
class CaseResult:
    """The complete retained result for one selected Benchmark Case."""

    case_id: int
    input: object
    output: object
    finish_reason: str | None
    grade: CaseGrade | None
    failures: tuple[Failure, ...]
    _metadata: Mapping[str, object] = field(repr=False)

    def __init__(
        self,
        *,
        case_id: int,
        input: object,
        output: object,
        finish_reason: str | None,
        grade: CaseGrade | None,
        failures: Sequence[Failure],
        metadata: Mapping[str, object],
    ) -> None:
        if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
            raise ValueError("Case Result case_id must be a positive integer")
        if grade is not None and not isinstance(grade, CaseGrade):
            raise TypeError("Case Result grade must be an sf.CaseGrade or None")
        if finish_reason is not None:
            finish_reason = _nonblank(finish_reason, "Case Result finish_reason")
        selected_failures = tuple(failures)
        if any(not isinstance(item, Failure) for item in selected_failures):
            raise TypeError("Case Result failures must contain sf.Failure values")
        if grade is None and not selected_failures:
            raise ValueError("an ungraded Case Result must contain a Failure")
        if grade is not None and selected_failures:
            raise ValueError("a graded Case Result cannot contain failures")
        values = {
            "case_id": case_id,
            "input": freeze_json(input, "Case Result input"),
            "output": freeze_json(output, "Case Result output"),
            "finish_reason": finish_reason,
            "grade": grade,
            "failures": selected_failures,
            "_metadata": freeze_mapping(metadata, "Case Result metadata"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def metadata(self) -> Mapping[str, object]:
        return self._metadata

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "input": thaw_json(self.input),
            "output": thaw_json(self.output),
            "finish_reason": self.finish_reason,
            "grade": None if self.grade is None else self.grade.to_dict(),
            "failures": [failure.to_dict() for failure in self.failures],
            "metadata": thaw_mapping(self._metadata),
        }


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _required_number(value, label)


def _required_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{label} must be a finite number")
    selected = float(value)
    if selected in {float("inf"), float("-inf")} or selected != selected:
        raise ValueError(f"{label} must be a finite number")
    return selected


__all__ = ["CaseGrade", "CaseResult", "Check", "Evidence", "EvidenceProducer"]
