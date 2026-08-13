"""Immutable, Benchmark-neutral Case Result values."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from screamingface._immutable_json import freeze_json, freeze_mapping, thaw_json, thaw_mapping
from screamingface._report_primitives import Failure, _nonblank

# The Engine's versioned wrapper for native multi-turn Candidate input; kept in lock-step
# with url4-cloud's `benchmarks/contract.py` CANDIDATE_INPUT_SCHEMA.
_CANDIDATE_INPUT_SCHEMA = "screamingface.candidate-input.v1"

type ProducerType = Literal["model", "deterministic"]

# The Engine's explicit per-Case outcome; kept in lock-step with url4-cloud's
# `benchmarks/contract.py` CaseStatus.
type CaseStatus = Literal["scored", "refused", "failed"]


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
    score: float | None
    checks: tuple[Check, ...]
    _metrics: Mapping[str, object] = field(repr=False)

    def __init__(
        self,
        *,
        method: str,
        score: float | None,
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
            "score": _optional_number(score, "Case Grade score"),
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

    status: CaseStatus
    case_id: int
    input: object
    output: object
    finish_reason: str | None
    refusal: str | None
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
        status: CaseStatus | None = None,
        refusal: str | None = None,
    ) -> None:
        if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
            raise ValueError("Case Result case_id must be a positive integer")
        if grade is not None and not isinstance(grade, CaseGrade):
            raise TypeError("Case Result grade must be an sf.CaseGrade or None")
        if finish_reason is not None:
            finish_reason = _nonblank(finish_reason, "Case Result finish_reason")
        if refusal is not None:
            refusal = _nonblank(refusal, "Case Result refusal")
        selected_failures = tuple(failures)
        if any(not isinstance(item, Failure) for item in selected_failures):
            raise TypeError("Case Result failures must contain sf.Failure values")
        _validate_case_state(grade, selected_failures)
        status = _resolve_case_status(status, refusal, grade)
        values = {
            "status": status,
            "case_id": case_id,
            "input": freeze_json(input, "Case Result input"),
            "output": freeze_json(output, "Case Result output"),
            "finish_reason": finish_reason,
            "refusal": refusal,
            "grade": grade,
            "failures": selected_failures,
            "_metadata": freeze_mapping(metadata, "Case Result metadata"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def metadata(self) -> Mapping[str, object]:
        return self._metadata

    @property
    def conversation(self) -> tuple[tuple[str, str], ...] | None:
        """The Case's chat turns, or ``None`` when the input is plain text.

        Engine-owned multi-turn Benchmarks (HealthBench first) wrap structured
        turns in the versioned candidate-input envelope; single-turn Benchmarks
        (DRACO, IFEval) send plain prompt text. This property is the SDK's ONE
        decode point for that wire format: it returns ``(role, content)`` turns
        only when the input is a JSON object explicitly carrying the envelope
        schema, and ``None`` for everything else — decoding never raises, so the
        worst case is seeing the raw string, never a crash. Renderers consume
        ``display_input`` / ``prompt_preview`` below and stay format-blind.
        """

        return _decode_candidate_envelope(self.input)

    @property
    def display_input(self) -> str:
        """The input as readable text: a role-labeled transcript, or the raw value."""

        turns = self.conversation
        if turns is None:
            return self.input if isinstance(self.input, str) else str(self.input)
        return "\n\n".join(f"{role}: {content}" for role, content in turns)

    @property
    def prompt_preview(self) -> str:
        """The Case's question — the first user turn, or the plain input text."""

        turns = self.conversation
        if turns is None:
            return self.input if isinstance(self.input, str) else str(self.input)
        for role, content in turns:
            if role == "user":
                return content
        return turns[0][1]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "case_id": self.case_id,
            "input": thaw_json(self.input),
            "output": thaw_json(self.output),
            "finish_reason": self.finish_reason,
            "refusal": self.refusal,
            "grade": None if self.grade is None else self.grade.to_dict(),
            "failures": [failure.to_dict() for failure in self.failures],
            "metadata": thaw_mapping(self._metadata),
        }


def _decode_candidate_envelope(value: object) -> tuple[tuple[str, str], ...] | None:
    """Decode the versioned chat envelope; ``None`` for anything that is not exactly it."""

    try:
        decoded = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        decoded = None
    envelope = (
        decoded
        if isinstance(decoded, Mapping) and decoded.get("schema") == _CANDIDATE_INPUT_SCHEMA
        else None
    )
    messages = envelope.get("messages") if envelope is not None else None
    parsed = [_turn(message) for message in messages] if isinstance(messages, list) else []
    turns = [turn for turn in parsed if turn is not None]
    # All-or-nothing: one malformed message means this is not a trustworthy
    # transcript — fall back to showing the raw string rather than a partial one.
    if not turns or len(turns) != len(parsed):
        return None
    return tuple(turns)


def _turn(message: object) -> tuple[str, str] | None:
    role = message.get("role") if isinstance(message, Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    return (role, content) if isinstance(role, str) and isinstance(content, str) else None


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _required_number(value, label)


def _required_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{label} must be a finite number")
    selected = float(value)
    if selected in {float("inf"), float("-inf")} or selected != selected:
        raise ValueError(f"{label} must be a finite number")
    return selected


def _validate_case_state(grade: CaseGrade | None, failures: Sequence[Failure]) -> None:
    if grade is None and not failures:
        raise ValueError("an ungraded Case Result must contain a Failure")
    if grade is not None and grade.score is None and not failures:
        raise ValueError("an unscored Case Grade must contain a Case Result Failure")
    if grade is not None and grade.score is not None and failures:
        raise ValueError("a graded Case Result cannot contain failures")


def _resolve_case_status(
    status: CaseStatus | None,
    refusal: str | None,
    grade: CaseGrade | None,
) -> CaseStatus:
    """Pin the Case's explicit outcome to the shape its grade and refusal imply.

    The Engine publishes `status` on the wire; a locally built value derives the
    same answer the Engine would (numeric grade → scored, refusal text → refused,
    otherwise failed) so the two can never disagree. An explicit status that
    contradicts the derived one is an ambiguous Case and is rejected.
    """

    derived: CaseStatus = (
        "scored"
        if grade is not None and grade.score is not None
        else "refused"
        if refusal is not None
        else "failed"
    )
    if derived == "scored" and refusal is not None:
        raise ValueError("a scored Case Result cannot contain refusal text")
    if status is None:
        return derived
    if status not in {"scored", "refused", "failed"}:
        raise ValueError("Case Result status must be 'scored', 'refused', or 'failed'")
    if status != derived:
        raise ValueError(f"Case Result status {status!r} contradicts its {derived!r} shape")
    return status


__all__ = ["CaseGrade", "CaseResult", "Check", "Evidence", "EvidenceProducer"]
