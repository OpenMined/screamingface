"""Task-local retrieval ceilings shared by Engine orchestration components."""

from __future__ import annotations

import contextvars
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """Whether retrieval is available and the domains it must never reach."""

    web_search: bool
    excluded_domains: tuple[str, ...] = ()


class RetrievalPolicyError(ValueError):
    """A nested invocation attempted to broaden its ambient retrieval ceiling."""


_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def normalize_excluded_domains(values: Sequence[str]) -> tuple[str, ...]:
    """Validate and canonicalize bare domains carried by retrieval policy."""

    if isinstance(values, (str, bytes)):
        raise ValueError("web_search_exclude must contain bare domains")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("web_search_exclude must contain bare domains")
        domain = value.strip().lower().removesuffix(".")
        try:
            ascii_domain = domain.encode("ascii").decode("ascii")
        except UnicodeEncodeError:
            raise ValueError("web_search_exclude must contain bare domains") from None
        labels = ascii_domain.split(".")
        if (
            not ascii_domain
            or len(ascii_domain) > 253
            or any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels)
        ):
            raise ValueError("web_search_exclude must contain bare domains")
        normalized.append(ascii_domain)
    return tuple(sorted(set(normalized)))


_policy: contextvars.ContextVar[RetrievalPolicy | None] = contextvars.ContextVar(
    "screamingface_engine_retrieval_policy", default=None
)


def current_retrieval_policy() -> RetrievalPolicy | None:
    """Return the effective policy for this task, or ``None`` outside orchestration."""

    return _policy.get()


@contextmanager
def retrieval_scope(requested: RetrievalPolicy) -> Iterator[RetrievalPolicy]:
    """Apply ``requested`` beneath the ambient ceiling and restore it on exit."""

    parent = _policy.get()
    if parent is not None and requested.web_search and not parent.web_search:
        raise RetrievalPolicyError(
            "nested Candidate Invocation cannot enable retrieval disabled by its parent"
        )
    effective = RetrievalPolicy(
        web_search=(
            requested.web_search if parent is None else parent.web_search and requested.web_search
        ),
        excluded_domains=tuple(
            sorted(
                {
                    *(parent.excluded_domains if parent is not None else ()),
                    *requested.excluded_domains,
                }
            )
        ),
    )
    token = _policy.set(effective)
    try:
        yield effective
    finally:
        _policy.reset(token)


__all__ = [
    "RetrievalPolicy",
    "RetrievalPolicyError",
    "current_retrieval_policy",
    "normalize_excluded_domains",
    "retrieval_scope",
]
