"""The App forwards the aigateway endpoint into every Runner Job (spec §9 env carriage).

FEATURE: a Runner Pod must reach the in-cluster aigateway Service. The Runner reads
``AIGATEWAY_BASE_URL`` (``url4_cloud_runner.__main__``) and otherwise falls back to
``http://127.0.0.1:9105`` — a loopback that resolves to the Runner's OWN pod, so without this
forwarding every scheduled run silently talks to nothing.

INVARIANT: the endpoint is deployment config carried by the App (ConfigMap → Settings → Job env),
never baked into an image — a baked value cannot follow the Service across namespaces/clusters.
"""

from typing import Any

from _k8s_fakes import FakeCreatedJob, fake_created_job

from url4_cloud.config import Settings
from url4_cloud.jobs.factory import build_job_runner
from url4_cloud.jobs.k8s import K8sJobRunner


class _RecordingBatchApi:
    """Captures the Job manifest the adapter would POST."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_job(self, namespace: str, body: Any) -> FakeCreatedJob:
        self.created.append(dict(body))
        return fake_created_job(f"uid-{body['metadata']['name']}")

    def read_namespaced_job(self, name: str, namespace: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


class _RecordingSecretsApi:
    """Stand-in for the ``CoreV1SecretsClient`` slice — unused by these tests (no ``.schedule()``
    call here forwards a credential), but ``build_job_runner`` always constructs one."""

    def create_namespaced_secret(self, namespace: str, body: Any) -> object:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_secret(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


def _job_env(api: _RecordingBatchApi) -> dict[str, str]:
    spec = api.created[0]["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: item["value"] for item in spec["env"]}


def test_k8s_job_env_carries_the_configured_aigateway_base_url() -> None:
    api = _RecordingBatchApi()
    runner = K8sJobRunner(
        api, image="url4-cloud:1", aigateway_base_url="http://aigateway.url4-cloud:9105"
    )

    runner.schedule("topic-a", "'hi'!'go'", 60)

    assert _job_env(api)["AIGATEWAY_BASE_URL"] == "http://aigateway.url4-cloud:9105"


def test_k8s_job_env_omits_aigateway_base_url_when_unset() -> None:
    # INVARIANT: absent config forwards nothing — the Runner keeps its own default rather than
    # inheriting an empty string that would break URL joining.
    api = _RecordingBatchApi()
    K8sJobRunner(api, image="url4-cloud:1").schedule("topic-a", "'hi'!'go'", 60)

    assert "AIGATEWAY_BASE_URL" not in _job_env(api)


def test_factory_threads_aigateway_base_url_from_settings() -> None:
    settings = Settings(runner="k8s", aigateway_base_url="http://aigateway.prod:9105")

    runner = build_job_runner(
        settings,
        k8s_client_factory=_RecordingBatchApi,
        k8s_secrets_client_factory=_RecordingSecretsApi,
    )

    assert isinstance(runner, K8sJobRunner)
    assert runner._aigateway_base_url == "http://aigateway.prod:9105"


def test_aigateway_base_url_defaults_to_unset() -> None:
    assert Settings().aigateway_base_url is None
