import hashlib
from abc import ABC, abstractmethod
from typing import Literal

_NAME_HASH_LEN = 16

JobStatus = Literal[
    "scheduled",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "stopped",
    "not_found",
]
"""The run states (spec §3): ``scheduled → running → {succeeded|failed|stopped|timed_out}``, plus
``not_found`` for an unknown/absent topic. Each adapter maps the substrate state it can observe."""


class JobAlreadyExists(Exception):
    pass


class JobRunnerAtCapacity(Exception):
    """The substrate refused the run because it is saturated — retry later, unchanged.

    Distinct from :class:`JobAlreadyExists`, which says THIS topic is spent and retrying can never
    help. This one is transient and carries no verdict about the request, so callers map it to a
    retry-after response rather than a conflict.

    Only substrates that own a finite local resource raise it — an in-process runner shares one
    event loop across every run it accepts, so admission is its own job. A cluster-backed runner
    lets the scheduler absorb the load and never raises.
    """

    def __init__(self, active: int, limit: int) -> None:
        super().__init__(f"runner at capacity: {active} run(s) in flight, limit {limit}")
        self.active = active
        self.limit = limit


def job_name(topic: str) -> str:
    digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:_NAME_HASH_LEN]
    return f"url4-{digest}"


class JobRunner(ABC):
    @abstractmethod
    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str: ...

    @abstractmethod
    def stop(self, topic: str) -> None: ...

    @abstractmethod
    def exists(self, topic: str) -> bool: ...

    @abstractmethod
    def status(self, topic: str) -> JobStatus: ...
