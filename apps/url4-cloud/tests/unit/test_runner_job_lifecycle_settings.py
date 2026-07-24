"""Runner Job resources + TTL settings, and their trip through the factory into the manifest.

FEATURE: a scheduled Runner Job is a well-behaved k8s citizen — it declares what it needs so
the scheduler can place it, and finished Jobs are eventually reclaimed instead of accumulating
one object per request forever.
"""

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job
from kubernetes.client import ApiException

from url4_cloud.config import Settings
from url4_cloud.jobs.factory import build_job_runner

TOPIC = "cap-topic"


class FakeBatchV1:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def create_namespaced_job(self, namespace: str, body) -> FakeCreatedJob:
        name = body["metadata"]["name"]
        self.jobs[name] = body
        return fake_created_job(f"uid-{name}")

    def read_namespaced_job(self, name: str, namespace: str):
        raise ApiException(status=404)

    def delete_namespaced_job(self, name: str, namespace: str) -> dict:
        return {}


class FakeCoreV1Secrets:
    """Unused by these tests (no ``.schedule()`` call here forwards a credential), but
    ``build_job_runner`` always constructs one."""

    def create_namespaced_secret(self, namespace: str, body) -> dict:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_secret(self, name: str, namespace: str) -> dict:  # pragma: no cover
        raise NotImplementedError


def _k8s_settings(**kw) -> Settings:
    return Settings(runner="k8s", namespace="url4", **kw)


def test_job_ttl_defaults_to_the_token_lifetime_plus_skew_margin() -> None:
    # INVARIANT: ttlSecondsAfterFinished counts from COMPLETION, and the Job already exists for
    # the whole run — so the guard only has to cover the post-completion window in which the
    # starting token could still be presented. That window is the token's own `exp`
    # (iat + iat_window_s); the extra 60s only absorbs App-vs-TTL-controller clock skew.
    settings = _k8s_settings(iat_window_s=60, job_deadline_s=57600)

    assert settings.effective_job_ttl_s == 120


def test_job_ttl_default_does_not_scale_with_the_run_deadline() -> None:
    # REGRESSION: the floor once included job_deadline_s, conflating "how long a RUN may take"
    # with "how long a spent token stays replayable". That retained ~960x more Job/Pod objects
    # than the guard needs. A longer deadline must not change the retention.
    short = _k8s_settings(iat_window_s=60, job_deadline_s=60)
    long = _k8s_settings(iat_window_s=60, job_deadline_s=57600)

    assert short.effective_job_ttl_s == long.effective_job_ttl_s == 120


def test_job_ttl_tracks_a_widened_iat_window() -> None:
    settings = _k8s_settings(iat_window_s=600, job_deadline_s=57600)

    assert settings.effective_job_ttl_s == 660


def test_job_ttl_may_be_extended_for_post_mortem_debugging() -> None:
    settings = _k8s_settings(iat_window_s=60, job_deadline_s=57600, job_ttl_s=100_000)

    assert settings.effective_job_ttl_s == 100_000


def test_job_ttl_below_the_token_lifetime_is_rejected_at_startup() -> None:
    # Reclaiming the Job while its token is still within `exp` re-opens replay. Refuse it where
    # it can still be fixed cheaply (process start) rather than on the first replayed request.
    with pytest.raises(ValueError, match="job_ttl_s"):
        _k8s_settings(iat_window_s=60, job_deadline_s=57600, job_ttl_s=30)


def test_job_ttl_exactly_at_the_token_lifetime_is_allowed() -> None:
    # iat_window_s is the true security bound — an operator may tune down to it, just not below.
    settings = _k8s_settings(iat_window_s=60, job_deadline_s=57600, job_ttl_s=60)

    assert settings.effective_job_ttl_s == 60


def test_k8s_runner_job_carries_the_configured_resources_and_ttl() -> None:
    client = FakeBatchV1()
    settings = _k8s_settings(
        iat_window_s=60,
        job_deadline_s=57600,
        runner_resources={
            "requests": {"cpu": "200m", "memory": "256Mi"},
            "limits": {"memory": "1Gi"},
        },
    )
    runner = build_job_runner(
        settings,
        k8s_client_factory=lambda: client,
        k8s_secrets_client_factory=FakeCoreV1Secrets,
    )
    assert runner is not None
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=57600)

    spec = client.jobs[name]["spec"]
    assert spec["ttlSecondsAfterFinished"] == 120
    container = spec["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"]["cpu"] == "200m"
    assert container["resources"]["limits"]["memory"] == "1Gi"


def test_k8s_runner_job_without_configured_resources_still_gets_its_ttl() -> None:
    client = FakeBatchV1()
    runner = build_job_runner(
        _k8s_settings(),
        k8s_client_factory=lambda: client,
        k8s_secrets_client_factory=FakeCoreV1Secrets,
    )
    assert runner is not None
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    spec = client.jobs[name]["spec"]
    assert spec["ttlSecondsAfterFinished"] == 120
    assert "resources" not in spec["template"]["spec"]["containers"][0]
