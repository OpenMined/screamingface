from dataclasses import dataclass


@dataclass(frozen=True)
class FakeObjectMeta:
    uid: str


@dataclass(frozen=True)
class FakeCreatedJob:
    metadata: FakeObjectMeta


def fake_created_job(uid: str) -> FakeCreatedJob:
    return FakeCreatedJob(metadata=FakeObjectMeta(uid=uid))
