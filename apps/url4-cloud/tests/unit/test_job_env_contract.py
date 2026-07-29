"""The App writes a Job's per-run env; `url4-cloud run` reads it back. This pins that round trip.

Both halves ship in one distribution now, so the pair of tests that existed only to catch two
hand-synced `job_env.py` copies drifting are gone — there is one module, and nothing to drift
from. What remains is what the merge did NOT make free: the App must write every REQUIRED name,
must write nothing the run mode does not read, must never inline a secret, and must leave the
deploy-time names to Helm.
"""

from typing import Any

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job

from url4_cloud import job_env
from url4_cloud.adapters.k8s import K8sJobRunner
from url4_cloud.runner.main import RunnerConfigError, params_from_env

pytestmark = pytest.mark.asyncio

TOPIC = "cap-topic"
EXPRESSION = "/model('x')!'go'"
NATS_URL = "nats://nats:4222"


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
    def create_namespaced_secret(
        self, namespace: str, body: Any, *, _request_timeout: float | None = None
    ) -> object:
        return object()

    def delete_namespaced_secret(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> object:  # pragma: no cover
        raise NotImplementedError


async def _scheduled_env(**extra: Any) -> dict[str, dict[str, Any]]:
    api = _RecordingBatchApi()
    runner = K8sJobRunner(
        api,
        image="runner:test",
        secrets_client=_RecordingSecretsApi(),
        **extra,
    )
    await runner.schedule(TOPIC, EXPRESSION, 60, credential="forwarded-token", profile="prof")
    container = api.created[0]["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index]
    return {entry["name"]: entry for entry in container["env"]}  # type: ignore[index]


async def test_every_variable_the_app_writes_is_one_the_runner_reads() -> None:
    written = set(await _scheduled_env())
    orphans = written - job_env.WRITTEN_BY_APP
    assert not orphans, (
        f"the App writes {sorted(orphans)} into the Job, but the Runner reads none of them — "
        f"either consume them there and add them to job_env.WRITTEN_BY_APP, or stop writing them"
    )


async def test_the_required_variables_are_always_written() -> None:
    written = set(await _scheduled_env())
    assert job_env.REQUIRED <= written, f"missing {sorted(job_env.REQUIRED - written)}"


async def test_the_runner_parses_exactly_what_the_app_wrote() -> None:
    scheduled = await _scheduled_env()
    env = {name: entry["value"] for name, entry in scheduled.items() if "value" in entry}

    params = params_from_env(env)

    assert params.topic == TOPIC
    assert params.url4 == EXPRESSION


async def test_the_runner_takes_its_nats_url_from_the_charts_env_not_the_app() -> None:
    """The App stopped writing it; `envFrom` supplies it, and the Runner cannot tell the source.

    Pinned from both directions so the fallback cannot quietly become the real behavior in prod:
    App-written env ALONE yields the loopback default, and the chart-injected value wins.
    """
    app_written = {
        name: entry["value"] for name, entry in (await _scheduled_env()).items() if "value" in entry
    }

    assert job_env.NATS_URL not in app_written
    assert params_from_env(app_written).nats_url == job_env.DEFAULT_NATS_URL

    from_chart = {**app_written, job_env.NATS_URL: NATS_URL}
    assert params_from_env(from_chart).nats_url == NATS_URL


def test_the_runner_rejects_an_env_missing_a_required_variable() -> None:
    env = dict.fromkeys(job_env.REQUIRED, "x")
    del env[job_env.TOPIC]
    with pytest.raises(RunnerConfigError, match=job_env.TOPIC):
        params_from_env(env)


async def test_secret_valued_variables_travel_by_reference_never_as_literals() -> None:
    scheduled = await _scheduled_env()
    checked = 0
    for name in job_env.SECRET:
        entry = scheduled.get(name)
        if entry is None:
            continue
        checked += 1
        assert "value" not in entry, f"{name} is a plaintext literal in the Job spec: {entry}"
        assert "secretKeyRef" in entry.get("valueFrom", {}), (
            f"{name} must be injected via valueFrom.secretKeyRef, got {entry}"
        )
    assert checked == len(job_env.SECRET), (
        f"expected this scheduling to forward all of {sorted(job_env.SECRET)}, saw {checked} — "
        f"the assertions above are vacuous otherwise"
    )


def test_the_two_env_populations_stay_disjoint() -> None:
    """Per-run and deploy-time are written by different parties; a name in both has two writers.

    Merging the packages removed the copies but not this hazard: `job_env` now declares both
    populations side by side, so a name added to the wrong frozenset is a one-character mistake
    that would have the App write a value Helm also writes — with `env` silently winning over
    `envFrom` and the chart's value never taking effect.
    """
    overlap = job_env.WRITTEN_BY_APP & job_env.DEPLOY_TIME
    assert not overlap, (
        f"{sorted(overlap)} is declared both per-run and deploy-time — the App's `env` shadows "
        f"the chart's `envFrom`, so Helm's value would be silently ignored"
    )


async def test_deploy_time_variables_are_not_written_by_the_app() -> None:
    """Helm owns these end-to-end; the App naming one would be two sources of truth again."""
    written = set(await _scheduled_env())

    assert not (written & job_env.DEPLOY_TIME), (
        f"the App writes {sorted(written & job_env.DEPLOY_TIME)} directly, but the chart injects "
        "them via envFrom — remove them from _env so Helm stays the only writer"
    )


async def test_the_job_inherits_the_charts_env_sources() -> None:
    api = _RecordingBatchApi()
    await K8sJobRunner(
        api, image="runner:test", env_configmap="url4-runner-env", env_secrets=("tavily",)
    ).schedule(TOPIC, EXPRESSION, 60)

    container = api.created[0]["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index]

    assert container["envFrom"] == [
        {"configMapRef": {"name": "url4-runner-env"}},
        {"secretRef": {"name": "tavily"}},
    ]


async def test_a_job_with_no_declared_env_sources_omits_env_from() -> None:
    api = _RecordingBatchApi()
    await K8sJobRunner(api, image="runner:test").schedule(TOPIC, EXPRESSION, 60)

    container = api.created[0]["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index]

    assert "envFrom" not in container
