"""Behaviour tests for the ``JobRunner`` composition root (spec §9 k8s deployment).

FEATURE: the deployed App schedules Runner Jobs — the substrate adapter is chosen from env
(``URL4_CLOUD_RUNNER``) rather than hardcoded, so prod (k8s) and the bus-only profile both
build from ONE composition root.

Headless (INFRA rule): the k8s client constructors are injected, so no in-cluster config load
is ever touched here.
"""

from collections.abc import Mapping
from typing import Any

import pytest

from url4_cloud.config import Settings
from url4_cloud.jobs import K8sJobRunner
from url4_cloud.jobs.factory import build_job_runner


class _FakeBatchApi:
    """Structural stand-in for ``kubernetes.client.BatchV1Api`` (the ``BatchV1JobsClient`` slice).

    Never driven here — these tests assert *what the factory built*, and the adapter's own calls
    are covered by ``test_jobs_k8s``.
    """

    def create_namespaced_job(
        self, namespace: str, body: Mapping[str, object]
    ) -> object:  # pragma: no cover
        raise NotImplementedError

    def read_namespaced_job(self, name: str, namespace: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


class _FakeCoreV1Api:
    """Structural stand-in for ``kubernetes.client.CoreV1Api``
    (the ``CoreV1SecretsClient`` slice)."""

    def create_namespaced_secret(
        self, namespace: str, body: Mapping[str, object]
    ) -> object:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_secret(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


def test_runner_none_builds_no_job_runner() -> None:
    # INVARIANT: the bus-only profile (compose app service) stays runner-less by default.
    assert build_job_runner(Settings(runner="none")) is None


def test_default_settings_build_no_job_runner() -> None:
    # WHY: an unset URL4_CLOUD_RUNNER must not silently try to reach a k8s substrate.
    assert build_job_runner(Settings()) is None


def test_k8s_runner_is_built_from_settings() -> None:
    settings = Settings(
        runner="k8s",
        namespace="url4-prod",
        runner_image="ghcr.io/openmined/url4-cloud:1.2.3",
        nats_url="nats://nats.url4-prod:4222",
    )
    loaded: list[bool] = []

    runner = build_job_runner(
        settings,
        k8s_client_factory=lambda: (loaded.append(True), _FakeBatchApi())[1],
        k8s_secrets_client_factory=_FakeCoreV1Api,
    )

    assert isinstance(runner, K8sJobRunner)
    # INVARIANT: the in-cluster credential load happens exactly once, at build time.
    assert loaded == [True]
    assert isinstance(runner._secrets_client, _FakeCoreV1Api)
    assert runner._namespace == "url4-prod"
    assert runner._image == "ghcr.io/openmined/url4-cloud:1.2.3"
    assert runner._nats_url == "nats://nats.url4-prod:4222"
    # INVARIANT: the Runner runs its OWN image via the url4-cloud-runner entrypoint (spec §9).
    assert runner._command == ["url4-cloud-runner"]


def test_unknown_runner_is_rejected_at_settings_construction() -> None:
    # INVARIANT: a typo'd substrate name fails fast at startup, never at first request.
    with pytest.raises(ValueError):
        Settings(runner="kubernetes")  # type: ignore[arg-type]
