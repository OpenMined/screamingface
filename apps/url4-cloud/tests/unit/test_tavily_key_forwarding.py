"""How the Tavily credential reaches a Runner Job — by reference, and named by the chart.

The Secret is deploy-time, so each Job attaches it whole with `envFrom.secretRef`. That injects
every key under its OWN name and cannot rename, which is why the Secret's key must literally be
`TAVILY_API_KEY` (the chart pins that; `tavily.secretKey` is gone).

The invariant that matters is unchanged and stricter than before: the credential is never a
literal in the Job spec. A Job object is readable with `get jobs` RBAC alone.
"""

from typing import Any

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job

from url4_cloud import job_env as runner_job_env
from url4_cloud.adapters.factory import build_job_runner
from url4_cloud.adapters.k8s import K8sJobRunner
from url4_cloud.config import Settings

pytestmark = pytest.mark.asyncio


class _RecordingBatchApi:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_job(
        self, namespace: str, body: Any, *, _request_timeout: float | None = None
    ) -> FakeCreatedJob:
        self.created.append(dict(body))
        return fake_created_job(f"uid-{body['metadata']['name']}")

    def read_namespaced_job(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(
        self,
        name: str,
        namespace: str,
        *,
        propagation_policy: str = "",
        _request_timeout: float | None = None,
    ) -> object:  # pragma: no cover
        raise NotImplementedError


class _RecordingSecretsApi:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_secret(
        self, namespace: str, body: Any, *, _request_timeout: float | None = None
    ) -> object:
        self.created.append(dict(body))
        return object()

    def delete_namespaced_secret(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> object:  # pragma: no cover
        raise NotImplementedError


def _container(api: _RecordingBatchApi) -> dict[str, Any]:
    return api.created[0]["spec"]["template"]["spec"]["containers"][0]


def _entry(api: _RecordingBatchApi, name: str) -> dict[str, Any] | None:
    return next((e for e in _container(api)["env"] if e["name"] == name), None)


async def test_the_job_attaches_the_tavily_secret_by_reference() -> None:
    api = _RecordingBatchApi()

    await K8sJobRunner(api, image="url4-cloud:kind", env_secrets=("url4-cloud-tavily",)).schedule(
        "topic-a", "(x)!go", 60
    )

    assert {"secretRef": {"name": "url4-cloud-tavily"}} in _container(api)["envFrom"]


async def test_the_credential_is_never_a_literal_in_the_job_spec() -> None:
    api = _RecordingBatchApi()

    await K8sJobRunner(api, image="url4-cloud:kind", env_secrets=("url4-cloud-tavily",)).schedule(
        "topic-a", "(x)!go", 60
    )

    assert "tvly-" not in repr(api.created[0])
    assert _entry(api, runner_job_env.TAVILY_API_KEY) is None, (
        "the App must not name TAVILY_API_KEY at all — envFrom injects it under the Secret's key"
    )


async def test_a_job_without_a_configured_secret_attaches_none() -> None:
    api = _RecordingBatchApi()

    await K8sJobRunner(api, image="url4-cloud:kind").schedule("topic-b", "(x)!go", 60)

    assert "envFrom" not in _container(api)


async def test_the_deploy_time_secret_does_not_disturb_the_per_run_credential() -> None:
    # Two different mechanisms on one Job: the Tavily Secret rides `envFrom` (deploy-time), the
    # caller's token stays an explicit `valueFrom.secretKeyRef` into a per-Job Secret.
    api = _RecordingBatchApi()
    runner = K8sJobRunner(
        api,
        image="url4-cloud:kind",
        env_secrets=("s",),
        secrets_client=_RecordingSecretsApi(),
    )

    await runner.schedule("topic-c", "(x)!go", 60, credential="cred-1")

    assert _entry(api, runner_job_env.TOPIC) == {
        "name": runner_job_env.TOPIC,
        "value": "topic-c",
    }
    token = _entry(api, runner_job_env.AIGATEWAY_TOKEN)
    assert token is not None
    assert "value" not in token
    assert token["valueFrom"]["secretKeyRef"]["key"] == "token"


def test_settings_build_a_runner_carrying_the_secret_name() -> None:
    settings = Settings(runner="k8s", tavily_secret_name="url4-cloud-tavily")

    runner = build_job_runner(
        settings,
        k8s_client_factory=_RecordingBatchApi,
        k8s_secrets_client_factory=_RecordingSecretsApi,
    )

    assert isinstance(runner, K8sJobRunner)
    assert runner._env_secrets == ["url4-cloud-tavily"]


def test_settings_without_a_secret_name_attach_no_secret() -> None:
    runner = build_job_runner(
        Settings(runner="k8s"),
        k8s_client_factory=_RecordingBatchApi,
        k8s_secrets_client_factory=_RecordingSecretsApi,
    )

    assert isinstance(runner, K8sJobRunner)
    assert runner._env_secrets == []
