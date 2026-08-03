"""The verifying-ensemble Candidate — check-and-retry instead of blend.

FEATURE: reproduces the ensemble of "Beyond Leaderboards: Tokenomics of Agentic
Small Language Model Ensembles" (Skurikhin et al., Los Alamos National Laboratory,
https://openreview.net/forum?id=XSIYfTm2h7) as a CANDIDATE: members answer in
parallel, the benchmark's deterministic verifier checks every draft mid-flight,
violations feed each member's retry (bounded attempts), a judge model tie-breaks
among passers, and deterministic engine actions return the winner verbatim.
STORY: as a researcher, I put a verifying ensemble and a solo model on the SAME
single-pass leaderboard column — the exam never changes, only the candidate does.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from screamingface.model import Model
from screamingface.recipe import Recipe, _name

MAX_ATTEMPTS = 3
_MIN_MEMBERS = 2
_MAX_MEMBERS = 4  # letters a-d — the select action's addressing space


@dataclass(frozen=True, slots=True, init=False, eq=False)
class CorrectiveEnsemble(Recipe):
    """N member Models in a bounded verifier-feedback retry loop, judge-tie-broken.

    Requires a benchmark that advertises verifier actions (e.g. ifeval); evaluating
    against any other benchmark raises a clear planning error.
    """

    name: str
    members: tuple[Model, ...]
    judge: Model

    def __init__(
        self,
        members: Sequence[Model],
        *,
        judge: Model,
        name: str | None = None,
    ) -> None:
        selected = _members(members)
        if not isinstance(judge, Model):
            raise TypeError("CorrectiveEnsemble judge must be an sf.Model")
        inferred = "+".join(member.name for member in selected) + " (corrective)"
        object.__setattr__(
            self,
            "name",
            inferred if name is None else _name(name, "corrective ensemble name"),
        )
        object.__setattr__(self, "members", selected)
        object.__setattr__(self, "judge", judge)

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        members = ", ".join(repr(member.name) for member in self.members)
        return f"CorrectiveEnsemble([{members}], judge={self.judge.name!r})"


def _members(values: object) -> tuple[Model, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("CorrectiveEnsemble members must be sf.Model values")
    selected = tuple(values)
    if not all(isinstance(member, Model) for member in selected):
        # WHY Models only: the checker grades each member's RAW draft — a nested
        # Fusion would hide its own members behind a synthesizer, which is exactly
        # the blending this recipe exists to avoid.
        raise TypeError("CorrectiveEnsemble members must be sf.Model values")
    if not _MIN_MEMBERS <= len(selected) <= _MAX_MEMBERS:
        raise ValueError(
            f"CorrectiveEnsemble needs {_MIN_MEMBERS}-{_MAX_MEMBERS} members, got {len(selected)}"
        )
    return selected


__all__ = ["MAX_ATTEMPTS", "CorrectiveEnsemble"]
