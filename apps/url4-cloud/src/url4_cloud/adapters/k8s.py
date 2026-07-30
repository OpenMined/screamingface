"""Kubernetes adapter for the `JobRunner` port (`url4.streaming.interfaces`): schedules one
Batch v1 Job per run, maps its live status to `JobStatus` (spec §3), and — via Core v1 —
manages the optional per-run credential Secret a Job's env forwards from."""

import asyncio
import contextlib
from collections.abc import Mapping, Sequence
from typing import Protocol

from kubernetes.client import ApiException

from url4.streaming.interfaces import JobAlreadyExists, JobStatus, job_name
from url4.streaming.trace import valid_traceparent
from url4_cloud import job_env
from url4_cloud.ports import IdentityAwareJobRunner

_CONFLICT = 409
_NOT_FOUND = 404

RUNNER_LABELS = {
    "app.kubernetes.io/name": "url4-runner",
    "app.kubernetes.io/part-of": "url4-cloud",
    "app.kubernetes.io/component": "job",
}

_CREDENTIAL_SECRET_KEY = "token"


def _credential_secret_name(job_name_: str) -> str:
    return f"{job_name_}-cred"


# WHY: narrow structural Protocols instead of the generated `kubernetes` client models — only
# the fields this adapter actually reads/writes, so callers (including tests) can supply fakes
# without importing or subclassing the real client types.
class _JobCondition(Protocol):
    @property
    def type(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def reason(self) -> str | None: ...


class _JobStatusView(Protocol):
    @property
    def active(self) -> int | None: ...
    @property
    def conditions(self) -> Sequence[_JobCondition] | None: ...


class _JobView(Protocol):
    @property
    def status(self) -> _JobStatusView | None: ...


class _CreatedObjectMeta(Protocol):
    @property
    def uid(self) -> str: ...


class _CreatedJob(Protocol):
    @property
    def metadata(self) -> _CreatedObjectMeta: ...


# `_request_timeout` is the generated kubernetes client's per-call deadline. It is spelled out in
# these Protocols (rather than passed through an untyped `**kwargs`) so that a call site which
# forgets it is a type error: every one of these is a blocking round trip running on a
# `to_thread` worker, and an un-deadlined one holds that worker until the process exits.
class BatchV1JobsClient(Protocol):
    def create_namespaced_job(
        self, namespace: str, body: Mapping[str, object], *, _request_timeout: float | None = None
    ) -> _CreatedJob: ...
    def read_namespaced_job(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> _JobView: ...
    # `propagation_policy` is required, not optional, and it is why this signature is spelled out:
    # batch/v1's server-side default is `orphanDependents`, kept for backwards compatibility, so a
    # delete that omits it removes the Job and LEAVES ITS POD RUNNING.
    def delete_namespaced_job(
        self,
        name: str,
        namespace: str,
        *,
        propagation_policy: str,
        _request_timeout: float | None = None,
    ) -> object: ...


class CoreV1SecretsClient(Protocol):
    def create_namespaced_secret(
        self, namespace: str, body: Mapping[str, object], *, _request_timeout: float | None = None
    ) -> object: ...
    def delete_namespaced_secret(
        self, name: str, namespace: str, *, _request_timeout: float | None = None
    ) -> object: ...


def _terminal_status(conditions: Sequence[_JobCondition] | None) -> JobStatus | None:
    """Reads the Job's `Complete`/`Failed` condition, if either has fired; `None` while running."""
    for cond in conditions or ():
        if cond.status != "True":
            continue
        if cond.type == "Complete":
            return "succeeded"
        if cond.type == "Failed":
            return "timed_out" if cond.reason == "DeadlineExceeded" else "failed"
    return None


def _map_status(job: _JobView | None) -> JobStatus:
    """Maps a Job's live state to `JobStatus` (spec §3): terminal condition first, else
    `running`/`scheduled` from whether a Pod is currently active, else `not_found`."""
    if job is None:
        return "not_found"
    view = job.status
    terminal = _terminal_status(view.conditions if view else None)
    if terminal is not None:
        return terminal
    return "running" if (view and view.active) else "scheduled"


class K8sJobRunner(IdentityAwareJobRunner):
    """Implements `JobRunner` by scheduling one Kubernetes Batch v1 Job per run. The Job's name
    is derived deterministically from the topic (`job_name`), so `schedule`/`stop`/`status` all
    address the same object without any separate lookup table."""

    def __init__(
        self,
        client: BatchV1JobsClient,
        *,
        image: str,
        namespace: str = "default",
        # WHY this default: the Job runs the App's OWN image in its run mode (`url4_cloud.cli`),
        # so the command is the mode switch and nothing else. It is pinned here, beside the Job
        # spec that uses it, rather than exposed as a chart value — the entrypoint belongs to the
        # image, and a values-file override could only ever name a mode the image does not have.
        command: Sequence[str] = ("url4-cloud", "run"),
        env_configmap: str | None = None,
        env_secrets: Sequence[str] = (),
        resources: Mapping[str, Mapping[str, str]] | None = None,
        job_ttl_s: int | None = None,
        min_job_ttl_s: int | None = None,
        secrets_client: CoreV1SecretsClient | None = None,
        request_timeout_s: float | None = None,
    ) -> None:
        self._client = client
        self._secrets_client = secrets_client
        self._request_timeout_s = request_timeout_s
        self._image = image
        self._namespace = namespace
        self._command = list(command)
        self._env_configmap = env_configmap
        self._env_secrets = list(env_secrets)
        self._resources = resources
        if job_ttl_s is not None and min_job_ttl_s is not None and job_ttl_s < min_job_ttl_s:
            raise ValueError(
                f"job_ttl_s={job_ttl_s} is below min_job_ttl_s={min_job_ttl_s} (the token's own "
                f"lifetime) — a Job reclaimed while its token is still valid re-opens replay"
            )
        self._job_ttl_s = job_ttl_s

    async def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
        identity: Mapping[str, str] | None = None,
    ) -> str:
        """Creates the Job (and, if a credential is given, its owned Secret).

        Raises:
            RuntimeError: a credential was given but no `secrets_client` was configured — this
                adapter refuses to fall back to injecting it as a plaintext Job env value.
            JobAlreadyExists: a Job for this topic already exists (409 from the API server).
        """
        return await asyncio.to_thread(
            self._schedule_blocking,
            topic,
            url4,
            deadline_s,
            traceparent=traceparent,
            credential=credential,
            profile=profile,
            identity=identity,
        )

    def _schedule_blocking(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
        identity: Mapping[str, str] | None = None,
    ) -> str:
        if credential and self._secrets_client is None:
            raise RuntimeError(
                "K8sJobRunner received a credential to forward but no secrets_client was "
                "configured — refusing to inject it as a plaintext Job env value"
            )
        name = job_name(topic)
        try:
            created = self._client.create_namespaced_job(
                self._namespace,
                self._manifest(
                    name, topic, url4, deadline_s, traceparent, credential, profile, identity
                ),
                _request_timeout=self._request_timeout_s,
            )
        except ApiException as exc:
            if exc.status == _CONFLICT:
                raise JobAlreadyExists(name) from exc
            raise
        if credential:
            try:
                self._create_credential_secret(name, created, credential)
            except ApiException:
                with contextlib.suppress(ApiException):
                    self._delete_job(name)
                raise
        return name

    def _create_credential_secret(
        self, job_name_: str, created_job: _CreatedJob, credential: str
    ) -> None:
        assert self._secrets_client is not None
        self._secrets_client.create_namespaced_secret(
            self._namespace,
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "type": "Opaque",
                "metadata": {
                    "name": _credential_secret_name(job_name_),
                    "labels": RUNNER_LABELS,
                    "ownerReferences": [
                        {
                            "apiVersion": "batch/v1",
                            "kind": "Job",
                            "name": job_name_,
                            "uid": created_job.metadata.uid,
                            "controller": True,
                            "blockOwnerDeletion": True,
                        }
                    ],
                },
                "stringData": {_CREDENTIAL_SECRET_KEY: credential},
            },
            _request_timeout=self._request_timeout_s,
        )

    async def stop(self, topic: str) -> None:
        await asyncio.to_thread(self._stop_blocking, topic)

    def _stop_blocking(self, topic: str) -> None:
        name = job_name(topic)
        # WHY the Job goes first now: deleting the Secret first leaves a window in which the Job
        # still exists but its `secretKeyRef` target does not. If the Job delete then fails, the
        # run is left permanently unable to start its container instead of simply still running.
        try:
            self._delete_job(name)
        except ApiException as exc:
            if exc.status != _NOT_FOUND:
                raise
        # The Secret carries an ownerReference on the Job, so k8s GC reclaims it on its own; this
        # is the prompt path, and a 404 here just means GC won the race.
        if self._secrets_client is not None:
            try:
                self._secrets_client.delete_namespaced_secret(
                    _credential_secret_name(name),
                    self._namespace,
                    _request_timeout=self._request_timeout_s,
                )
            except ApiException as exc:
                if exc.status != _NOT_FOUND:
                    raise

    def _delete_job(self, name: str) -> None:
        """Delete a Job AND the Pod running it.

        INVARIANT: `propagation_policy="Background"` is mandatory. batch/v1 declares
        `DefaultGarbageCollectionPolicy: OrphanDependents`, so a delete that omits the policy
        removes the Job object and leaves its Pod running — still evaluating the expression, still
        publishing frames, still spending the caller's model credit, with `activeDeadlineSeconds`
        gone along with the Job that carried it. It is also invisible afterwards: `exists()` reads
        the Job, so it reports `not_found` while the Pod runs on, and the topic can be scheduled
        again while the first run is live. This is why `kubectl delete job` passes
        `--cascade=background` explicitly rather than relying on the default.
        """
        self._client.delete_namespaced_job(
            name,
            self._namespace,
            propagation_policy="Background",
            _request_timeout=self._request_timeout_s,
        )

    async def exists(self, topic: str) -> bool:
        return await asyncio.to_thread(self._read, topic) is not None

    async def status(self, topic: str) -> JobStatus:
        return _map_status(await asyncio.to_thread(self._read, topic))

    def _read(self, topic: str) -> _JobView | None:
        try:
            return self._client.read_namespaced_job(
                job_name(topic), self._namespace, _request_timeout=self._request_timeout_s
            )
        except ApiException as exc:
            if exc.status == _NOT_FOUND:
                return None
            raise

    def _env(
        self,
        name: str,
        topic: str,
        url4: str,
        deadline_s: int,
        traceparent: str | None,
        credential: str | None = None,
        profile: str | None = None,
        identity: Mapping[str, str] | None = None,
    ) -> list[dict[str, object]]:
        # INVARIANT: PER-RUN values only. Everything constant for a deployment (the NATS URL, the
        # aigateway base URL and model, the Tavily key) arrives through `envFrom` — Helm owns both
        # its name and its value, so the App never learns those names. What is left here is what
        # Helm cannot know: it does not exist until someone submits a run.
        env: list[dict[str, object]] = [
            {"name": job_env.TOPIC, "value": topic},
            {"name": job_env.EXPRESSION, "value": url4},
            {"name": job_env.JOB_DEADLINE_S, "value": str(deadline_s)},
        ]
        forwarded_traceparent = valid_traceparent(traceparent)
        if forwarded_traceparent is not None:
            env.append({"name": job_env.TRACEPARENT, "value": forwarded_traceparent})
        if credential:
            env.append(
                {
                    "name": job_env.AIGATEWAY_TOKEN,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": _credential_secret_name(name),
                            "key": _CREDENTIAL_SECRET_KEY,
                        }
                    },
                }
            )
        if profile is not None:
            env.append({"name": job_env.AIGATEWAY_PROFILE, "value": profile})
        # Plain `value`, deliberately — unlike the credential above, identity authorizes nothing on
        # its own, and a Secret would imply a confidentiality it does not have (see
        # `job_env.IDENTITY_HEADER_ENV`). It is absent from `job_env.SECRET` for the same reason,
        # which is what lets `test_job_env_contract` keep asserting that every SECRET name travels
        # by reference.
        env.extend(
            {"name": name, "value": value}
            for name, value in job_env.identity_to_env(identity or {}).items()
        )
        return env

    def _env_from(self) -> list[dict[str, object]]:
        """The deploy-time env sources the Job inherits wholesale.

        `envFrom` injects every key of a ConfigMap/Secret under its OWN name, which is the point:
        the chart is the single place a deploy-time Runner variable is named. Ordering matters
        only against `env`, which always wins — so a per-run value can never be shadowed.
        """
        sources: list[dict[str, object]] = []
        if self._env_configmap is not None:
            sources.append({"configMapRef": {"name": self._env_configmap}})
        sources.extend({"secretRef": {"name": name}} for name in self._env_secrets)
        return sources

    def _manifest(
        self,
        name: str,
        topic: str,
        url4: str,
        deadline_s: int,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
        identity: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        """Builds the Job manifest: a hardened, single-attempt Pod (no restarts, no privilege
        escalation, non-root, read-only rootfs) running `self._command` with per-run env layered
        over the deploy-time `envFrom` sources, and an optional `ttlSecondsAfterFinished`."""
        container: dict[str, object] = {
            "name": "runner",
            "image": self._image,
            "command": self._command,
            "env": self._env(
                name, topic, url4, deadline_s, traceparent, credential, profile, identity
            ),
            "securityContext": {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "readOnlyRootFilesystem": True,
            },
            "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
        }
        env_from = self._env_from()
        if env_from:
            container["envFrom"] = env_from
        if self._resources is not None:
            container["resources"] = {k: dict(v) for k, v in self._resources.items()}
        spec: dict[str, object] = {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline_s,
            "template": {
                "metadata": {"labels": RUNNER_LABELS},
                "spec": {
                    "restartPolicy": "Never",
                    "enableServiceLinks": False,
                    "automountServiceAccountToken": False,
                    "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [container],
                    "volumes": [{"name": "tmp", "emptyDir": {}}],
                },
            },
        }
        if self._job_ttl_s is not None:
            spec["ttlSecondsAfterFinished"] = self._job_ttl_s
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "labels": RUNNER_LABELS},
            "spec": spec,
        }
