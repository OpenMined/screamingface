"""Runner Jobs must not inherit kubelet's legacy Docker-link Service env (spec §9).

FEATURE: a Runner Job is configured ONLY by what the App puts in its env.

INVARIANT: kubelet exports one ``{SERVICE_NAME}_PORT=tcp://<ip>:<port>`` per Service in the
namespace unless ``enableServiceLinks: false``. The App's Service is ``url4-cloud``, which yields
``URL4_CLOUD_PORT`` — colliding with this project's own ``URL4_CLOUD_`` settings prefix. The App
Deployment hit exactly that (crash on ``int("tcp://10.96.x.x:9108")``); Jobs read the same
``URL4_CLOUD_*`` namespace, so they are pinned here too rather than left to luck.
"""

from typing import Any

from url4_cloud.jobs.k8s import K8sJobRunner


class _RecordingBatchApi:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_job(self, namespace: str, body: Any) -> object:
        self.created.append(dict(body))
        return object()

    def read_namespaced_job(self, name: str, namespace: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


def _pod_spec(api: _RecordingBatchApi) -> dict[str, Any]:
    return api.created[0]["spec"]["template"]["spec"]


def test_runner_job_disables_service_link_env_injection() -> None:
    api = _RecordingBatchApi()
    K8sJobRunner(api, image="url4-cloud:1").schedule("topic-a", "'hi'!'go'", 60)

    assert _pod_spec(api)["enableServiceLinks"] is False


def test_runner_job_env_is_exactly_what_the_app_set() -> None:
    """The Job carries only the App-supplied contract keys — no ambient Service noise."""
    api = _RecordingBatchApi()
    K8sJobRunner(api, image="url4-cloud:1", nats_url="nats://nats:4222").schedule(
        "topic-a", "'hi'!'go'", 60
    )

    names = {e["name"] for e in _pod_spec(api)["containers"][0]["env"]}
    assert names == {
        "URL4_CLOUD_TOPIC",
        "URL4_CLOUD_EXPRESSION",
        "URL4_CLOUD_JOB_DEADLINE_S",
        "URL4_CLOUD_NATS_URL",
    }
