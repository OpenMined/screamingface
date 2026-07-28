"""Wires the `JobRunner` port to its concrete adapter for the deployment at hand.

# INVARIANT: this is the one place a concrete `JobRunner` implementation gets chosen and
# constructed — everything else in the app depends only on the port, never on `K8sJobRunner`
# (or any future adapter) directly.
"""

import functools
from collections.abc import Callable
from typing import Any, cast

from url4.streaming.interfaces import JobRunner
from url4_cloud.adapters.k8s import BatchV1JobsClient, CoreV1SecretsClient, K8sJobRunner
from url4_cloud.config import Settings


@functools.cache
def _in_cluster_api_client() -> Any:  # pragma: no cover - live cluster (INFRA)
    """The process's single kubernetes ApiClient — one config load, one connection pool.

    Built once and shared: two `ApiClient`s would mean two TLS pools and two lazily-spawned
    thread pools held for the life of the process, for one API server.
    """
    from kubernetes.client import ApiClient
    from kubernetes.config import load_incluster_config

    load_incluster_config()
    return ApiClient()


def _in_cluster_batch_client() -> BatchV1JobsClient:  # pragma: no cover - live cluster (INFRA)
    from kubernetes.client import BatchV1Api

    return cast(BatchV1JobsClient, BatchV1Api(_in_cluster_api_client()))


def _in_cluster_secrets_client() -> CoreV1SecretsClient:  # pragma: no cover - live cluster (INFRA)
    from kubernetes.client import CoreV1Api

    return cast(CoreV1SecretsClient, CoreV1Api(_in_cluster_api_client()))


def build_job_runner(
    settings: Settings,
    *,
    k8s_client_factory: Callable[[], BatchV1JobsClient] = _in_cluster_batch_client,
    k8s_secrets_client_factory: Callable[[], CoreV1SecretsClient] = _in_cluster_secrets_client,
) -> JobRunner | None:
    """Selects the `JobRunner` adapter for `settings.runner`.

    Returns `None` when no runner is configured (e.g. local mode, where nothing schedules
    Jobs) rather than raising — callers decide whether the absence of a runner is fatal.
    """
    if settings.runner == "k8s":
        # WHY: `command` is left to K8sJobRunner's default — the image entrypoint has one
        # source of truth, and it is next to the Job spec that uses it.
        return K8sJobRunner(
            k8s_client_factory(),
            image=settings.runner_image,
            namespace=settings.namespace,
            env_configmap=settings.runner_env_configmap,
            env_secrets=(settings.tavily_secret_name,) if settings.tavily_secret_name else (),
            resources=settings.runner_resources,
            job_ttl_s=settings.effective_job_ttl_s,
            min_job_ttl_s=settings.iat_window_s,
            secrets_client=k8s_secrets_client_factory(),
        )
    return None
