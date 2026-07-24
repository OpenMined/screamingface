"""Test-only value objects for the ``BatchV1JobsClient`` slice (not shipped).

``kubernetes.client.BatchV1Api.create_namespaced_job`` answers with the created ``V1Job``, and
:class:`~url4_cloud.jobs.k8s.K8sJobRunner` reads exactly one field off it — ``metadata.uid`` — to
seed the ``ownerReference`` on the per-run credential Secret. Every batch-API fake therefore has to
answer with something carrying that field (the ``_CreatedJob`` protocol in ``jobs/k8s.py``); this is
that stand-in, shared so the fakes across the k8s test modules agree on ONE shape instead of each
inventing (or, worse, eliding) its own.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FakeObjectMeta:
    uid: str


@dataclass(frozen=True)
class FakeCreatedJob:
    """The created-Job view ``K8sJobRunner`` reads — the ``_CreatedJob`` protocol's ``metadata``."""

    metadata: FakeObjectMeta


def fake_created_job(uid: str) -> FakeCreatedJob:
    """``FakeCreatedJob`` from a bare uid — the one-liner the batch-API fakes return."""
    return FakeCreatedJob(metadata=FakeObjectMeta(uid=uid))
