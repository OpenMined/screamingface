from dataclasses import dataclass

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job
from kubernetes.client import ApiException

from url4.streaming.interfaces import JobAlreadyExists, JobRunner, job_name
from url4_cloud import job_env
from url4_cloud.adapters.k8s import K8sJobRunner

pytestmark = pytest.mark.asyncio

TOPIC = "cap-topic"


@dataclass
class FakeCondition:
    type: str
    status: str
    reason: str | None = None


@dataclass
class FakeJobStatus:
    active: int | None = None
    conditions: list[FakeCondition] | None = None


@dataclass
class FakeJob:
    status: FakeJobStatus | None = None


class FakeBatchV1:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.states: dict[str, FakeJob] = {}
        self.deleted: list[str] = []
        self.delete_policies: list[str] = []

    def create_namespaced_job(
        self, namespace: str, body, *, _request_timeout: float | None = None
    ) -> FakeCreatedJob:
        name = body["metadata"]["name"]
        if name in self.jobs:
            raise ApiException(status=409)
        self.jobs[name] = body
        return fake_created_job(f"uid-{name}")

    def read_namespaced_job(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> FakeJob:
        if name not in self.jobs:
            raise ApiException(status=404)
        return self.states.get(name, FakeJob())

    def delete_namespaced_job(
        self,
        name: str,
        namespace: str,
        *,
        propagation_policy: str = "",
        _request_timeout: float | None = None,
    ) -> dict:
        if name not in self.jobs:
            raise ApiException(status=404)
        del self.jobs[name]
        self.deleted.append(name)
        self.delete_policies.append(propagation_policy)
        return {}


class FakeCoreV1Secrets:
    def __init__(self) -> None:
        self.secrets: dict[str, dict] = {}
        self.deleted: list[str] = []

    def create_namespaced_secret(
        self, namespace: str, body, *, _request_timeout: float | None = None
    ) -> dict:
        name = body["metadata"]["name"]
        self.secrets[name] = body
        return body

    def delete_namespaced_secret(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> dict:
        if name not in self.secrets:
            raise ApiException(status=404)
        del self.secrets[name]
        self.deleted.append(name)
        return {}


def _runner(client: FakeBatchV1, secrets_client: FakeCoreV1Secrets | None = None) -> K8sJobRunner:
    return K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        env_configmap="url4-cloud-runner-env",
        secrets_client=secrets_client if secrets_client is not None else FakeCoreV1Secrets(),
    )


def test_runner_satisfies_the_port() -> None:
    runner: JobRunner = _runner(FakeBatchV1())
    assert isinstance(runner, JobRunner)


async def test_schedule_builds_a_run_once_named_spec() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=57600)

    assert name == job_name(TOPIC)
    manifest = client.jobs[name]
    assert manifest["metadata"]["name"] == name
    spec = manifest["spec"]
    assert spec["backoffLimit"] == 0
    assert spec["activeDeadlineSeconds"] == 57600
    pod = spec["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    container = pod["containers"][0]
    assert container["image"] == "registry/url4-cloud:1"
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env[job_env.TOPIC] == TOPIC
    assert env[job_env.EXPRESSION] == "chat(hi)"
    # The NATS URL is deploy-time: the chart names and values it, the Job inherits it wholesale.
    assert container["envFrom"] == [{"configMapRef": {"name": "url4-cloud-runner-env"}}]


def _container_env_entries(client: FakeBatchV1, name: str) -> list[dict]:
    manifest = client.jobs[name]
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    return container["env"]


def _container_env(client: FakeBatchV1, name: str) -> dict[str, str]:
    return {e["name"]: e["value"] for e in _container_env_entries(client, name) if "value" in e}


async def test_schedule_with_credential_and_profile_sets_env() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok", profile="p")

    env = _container_env(client, name)
    assert job_env.AIGATEWAY_TOKEN not in env
    assert env[job_env.AIGATEWAY_PROFILE] == "p"

    entries = {e["name"]: e for e in _container_env_entries(client, name)}
    token_ref = entries[job_env.AIGATEWAY_TOKEN]["valueFrom"]["secretKeyRef"]
    assert token_ref == {"name": f"{name}-cred", "key": "token"}
    assert secrets.secrets[f"{name}-cred"]["stringData"] == {"token": "tok"}
    owner_ref = secrets.secrets[f"{name}-cred"]["metadata"]["ownerReferences"][0]
    assert owner_ref["name"] == name
    assert owner_ref["uid"] == f"uid-{name}"


async def test_schedule_without_credential_omits_aigateway_env() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    env = _container_env(client, name)
    assert job_env.AIGATEWAY_TOKEN not in env
    assert job_env.AIGATEWAY_PROFILE not in env
    assert secrets.secrets == {}


async def test_schedule_with_credential_but_no_secrets_client_fails_loud() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(client, image="registry/url4-cloud:1", namespace="url4")

    with pytest.raises(RuntimeError, match="secrets_client"):
        await runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")

    assert client.jobs == {}


async def test_stop_deletes_the_credential_secret_alongside_the_job() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")
    assert f"{name}-cred" in secrets.secrets

    await runner.stop(TOPIC)

    assert f"{name}-cred" not in secrets.secrets
    assert client.deleted == [name]
    await runner.stop(TOPIC)


async def test_stop_without_a_forwarded_credential_never_touches_secrets() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    await runner.stop(TOPIC)

    assert secrets.deleted == []


async def test_secret_create_failure_deletes_the_just_created_job_and_reraises() -> None:
    class BoomSecrets(FakeCoreV1Secrets):
        def create_namespaced_secret(
            self, namespace: str, body, *, _request_timeout: float | None = None
        ) -> dict:
            raise ApiException(status=500)

    client = FakeBatchV1()
    runner = _runner(client, BoomSecrets())

    with pytest.raises(ApiException):
        await runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")

    assert client.jobs == {}
    assert client.deleted == [job_name(TOPIC)]


async def test_schedule_twice_is_the_stateless_single_use_guard() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    with pytest.raises(JobAlreadyExists):
        await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)


async def test_exists_reflects_the_scheduled_job() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    assert await runner.exists(TOPIC) is False
    await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    assert await runner.exists(TOPIC) is True


async def test_stop_deletes_the_job_and_is_idempotent() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    await runner.stop(TOPIC)
    assert client.deleted == [job_name(TOPIC)]
    assert await runner.exists(TOPIC) is False
    await runner.stop(TOPIC)


async def _schedule_with_state(state: FakeJobStatus | None) -> K8sJobRunner:
    client = FakeBatchV1()
    runner = _runner(client)
    await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    if state is not None:
        client.states[job_name(TOPIC)] = FakeJob(status=state)
    return runner


async def test_status_not_found_for_unknown_topic() -> None:
    runner = _runner(FakeBatchV1())
    assert await runner.status(TOPIC) == "not_found"


async def test_status_scheduled_when_no_status_yet() -> None:
    runner = await _schedule_with_state(None)
    assert await runner.status(TOPIC) == "scheduled"


async def test_status_running_when_active() -> None:
    runner = await _schedule_with_state(FakeJobStatus(active=1))
    assert await runner.status(TOPIC) == "running"


async def test_status_succeeded_on_complete_condition() -> None:
    runner = await _schedule_with_state(
        FakeJobStatus(conditions=[FakeCondition(type="Complete", status="True")])
    )
    assert await runner.status(TOPIC) == "succeeded"


async def test_status_failed_on_failed_condition() -> None:
    runner = await _schedule_with_state(
        FakeJobStatus(
            conditions=[FakeCondition(type="Failed", status="True", reason="BackoffLimitExceeded")]
        )
    )
    assert await runner.status(TOPIC) == "failed"


async def test_status_timed_out_on_deadline_exceeded() -> None:
    runner = await _schedule_with_state(
        FakeJobStatus(
            conditions=[FakeCondition(type="Failed", status="True", reason="DeadlineExceeded")]
        )
    )
    assert await runner.status(TOPIC) == "timed_out"


async def test_status_ignores_a_false_condition() -> None:
    runner = await _schedule_with_state(
        FakeJobStatus(active=1, conditions=[FakeCondition(type="Complete", status="False")])
    )
    assert await runner.status(TOPIC) == "running"


async def test_status_reraises_non_404_api_errors() -> None:
    class Boom(FakeBatchV1):
        def read_namespaced_job(
            self, name: str, namespace: str, *, _request_timeout: float | None = None
        ) -> FakeJob:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        await runner.status(TOPIC)


async def test_schedule_reraises_non_409_api_errors() -> None:
    class Boom(FakeBatchV1):
        def create_namespaced_job(
            self, namespace: str, body, *, _request_timeout: float | None = None
        ) -> FakeCreatedJob:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)


async def test_stop_reraises_non_404_api_errors() -> None:
    class Boom(FakeBatchV1):
        def delete_namespaced_job(
            self,
            name: str,
            namespace: str,
            *,
            propagation_policy: str = "",
            _request_timeout: float | None = None,
        ) -> dict:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        await runner.stop(TOPIC)


def _pod(client: FakeBatchV1, name: str) -> dict:
    return client.jobs[name]["spec"]["template"]["spec"]


async def test_runner_job_container_is_hardened_like_the_app() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    sec = _pod(client, name)["containers"][0]["securityContext"]
    assert sec["allowPrivilegeEscalation"] is False
    assert sec["capabilities"] == {"drop": ["ALL"]}
    assert sec["runAsNonRoot"] is True
    assert sec["runAsUser"] == 1000
    assert sec["readOnlyRootFilesystem"] is True


async def test_runner_job_pod_sets_the_restricted_seccomp_profile() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert _pod(client, name)["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}


async def test_runner_job_mounts_a_writable_tmp_for_the_read_only_root() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    pod = _pod(client, name)
    assert {"name": "tmp", "emptyDir": {}} in pod["volumes"]
    mounts = pod["containers"][0]["volumeMounts"]
    assert {"name": "tmp", "mountPath": "/tmp"} in mounts


async def test_runner_job_does_not_mount_a_serviceaccount_token() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert _pod(client, name)["automountServiceAccountToken"] is False


async def test_runner_job_carries_the_configured_resources() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        resources={"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}},
    )
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    container = _pod(client, name)["containers"][0]
    assert container["resources"] == {
        "requests": {"cpu": "200m", "memory": "256Mi"},
        "limits": {"memory": "1Gi"},
    }


async def test_runner_job_omits_resources_when_unset() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert "resources" not in _pod(client, name)["containers"][0]


async def test_runner_job_ttl_is_forwarded_so_finished_jobs_are_reclaimed() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(client, image="registry/url4-cloud:1", namespace="url4", job_ttl_s=57660)
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert client.jobs[name]["spec"]["ttlSecondsAfterFinished"] == 57660


def test_runner_rejects_a_job_ttl_below_min_job_ttl_at_construction() -> None:
    with pytest.raises(ValueError, match="job_ttl_s=30 is below min_job_ttl_s=60"):
        K8sJobRunner(
            FakeBatchV1(),
            image="registry/url4-cloud:1",
            namespace="url4",
            job_ttl_s=30,
            min_job_ttl_s=60,
        )


async def test_runner_accepts_a_job_ttl_at_or_above_min_job_ttl() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        job_ttl_s=60,
        min_job_ttl_s=60,
    )
    name = await runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    assert client.jobs[name]["spec"]["ttlSecondsAfterFinished"] == 60


async def test_runner_job_omits_ttl_when_unset_so_the_replay_guard_never_expires() -> None:
    client = FakeBatchV1()
    name = await _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert "ttlSecondsAfterFinished" not in client.jobs[name]["spec"]


async def test_stop_deletes_the_pod_too_not_just_the_job() -> None:
    """REGRESSION (C1): `stop` must cascade to the Pod, or the run does not actually stop.

    batch/v1 declares `DefaultGarbageCollectionPolicy: OrphanDependents`, so a delete that omits
    `propagation_policy` removes the Job object and leaves its Pod running — still evaluating the
    expression, still publishing frames, still spending the caller's model credit, and now with no
    `activeDeadlineSeconds` to bound it because that lived on the Job. `exists()` reads the Job, so
    the orphan is invisible and the topic can be scheduled again while the first run is still live.

    Asserting the policy reaches the client is the only way to see this without a cluster: the Job
    disappears either way, so every other observable in the fake is identical.
    """
    api = FakeBatchV1()
    runner = K8sJobRunner(api, image="runner:test")
    await runner.schedule(TOPIC, "/m('x')!'go'", 60)

    await runner.stop(TOPIC)

    assert api.delete_policies == ["Background"]


async def test_stop_deletes_the_job_before_its_credential_secret() -> None:
    """Ordering matters: a Job whose `secretKeyRef` target is already gone cannot start its
    container, so deleting the Secret first turns a failed Job-delete into a permanently stuck run
    rather than one that is merely still running. The Secret's ownerReference means k8s reclaims
    it regardless, so the Job is the one that has to go first."""
    api = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = K8sJobRunner(api, image="runner:test", secrets_client=secrets)
    await runner.schedule(TOPIC, "/m('x')!'go'", 60, credential="tok")

    order: list[str] = []
    api_delete, secret_delete = api.delete_namespaced_job, secrets.delete_namespaced_secret
    api.delete_namespaced_job = lambda *a, **k: (order.append("job"), api_delete(*a, **k))[1]  # type: ignore[method-assign]
    secrets.delete_namespaced_secret = lambda *a, **k: (  # type: ignore[method-assign]
        order.append("secret"),
        secret_delete(*a, **k),
    )[1]

    await runner.stop(TOPIC)

    assert order == ["job", "secret"]
