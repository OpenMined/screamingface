"""url4-cloud application settings (env-prefixed ``URL4_CLOUD_``)."""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# WHY a margin at all: the App decides a token is expired from its own clock, while the k8s TTL
# controller deletes the Job from the control plane's. Without slack a skewed pair could reclaim
# the guard a few seconds before the token is actually refused. 60s is far beyond realistic
# in-cluster skew and still ~500x cheaper than the old job_deadline_s-based floor.
_TTL_SKEW_MARGIN_S = 60

RunnerBackend = Literal["none", "k8s"]
"""Which ``JobRunner`` substrate the deployed App schedules runs on (spec §9).

``k8s`` is prod (namespace-scoped batch/v1 Jobs) and ``none`` a bus-only App that mints tokens
and bridges NATS but schedules nothing.
"""

# WHY a named module constant (not a bare literal) for the insecure default: the prod guard in
# app.py (_require_prod_secret) compares against this same sentinel so the two never drift. If the
# default changes and the guard isn't updated, a prod boot would silently proceed on the weak
# secret.
INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    """Runtime configuration; overridable via ``URL4_CLOUD_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="URL4_CLOUD_")

    # WHY: HS256 signing secret for the JWT topic-capability token (spec §4). Never logged.
    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    nats_url: str = "nats://localhost:4222"
    # INVARIANT: stateless iat window (seconds) — start rejected when now - iat exceeds it (§4).
    iat_window_s: int = 60
    # WHY: sync-hold cap; a run outliving it degrades to 202 async (spec §5).
    sync_max_wait_s: float = 30.0
    # WHY: idle interval between WS HeartbeatEvents for liveness (spec §6).
    ws_heartbeat_s: float = 15.0
    # INVARIANT: k8s Job activeDeadlineSeconds ceiling = 16h (spec §3).
    job_deadline_s: int = 57600
    # WHY: the run substrate is deployment-shaped, not code-shaped — the helm chart sets `k8s`.
    # Default `none` keeps a bare `Settings()` from reaching for a cluster.
    runner: RunnerBackend = "none"
    # INVARIANT: the App's RBAC Role is namespace-scoped, so Jobs are only ever created here (§9).
    namespace: str = "default"
    # WHY: the Runner is its OWN image now (apps/url4-cloud/runner/Dockerfile), entered through
    # the `url4-cloud-runner` console script — so this is that image's tag. The backend
    # schedules it as a batch/v1 Job per run (K8sJobRunner._manifest).
    runner_image: str = "url4-cloud-runner:latest"
    # WHY: forwarded into every Runner Job as AIGATEWAY_BASE_URL. The Runner's own fallback is
    # loopback (127.0.0.1:9105), which inside a Job Pod resolves to itself — so an in-cluster
    # deployment MUST supply the aigateway Service URL here. `None` = forward nothing and let the
    # Runner keep its default (the local/dev shape).
    aigateway_base_url: str | None = None
    # --- Tavily web tools (spec 2026-07-23). The connector declares web_search/web_fetch ONLY
    # when the Runner sees TAVILY_API_KEY; unset here => deny-by-default (dec:W5).
    #
    # WHY a reference (not a value): a ``batch/v1`` Job object is NOT a secret — readable with
    # ``get jobs`` RBAC (far looser than ``get secrets``) and surfaced in ``kubectl describe``/
    # ``-o yaml`` and the create-call audit log — so the key travels as a Secret *reference*, not
    # a literal copied into the manifest (see ``K8sJobRunner._env``). The name/key of the Secret
    # the Runner Job's env references:
    tavily_secret_name: str | None = None
    tavily_secret_key: str = "api-key"
    # WHY: the Runner drives the url4 DAG engine and buffers model responses — it is the
    # workload that actually consumes CPU/memory here. Without requests it schedules into the
    # BestEffort QoS class (placed blind, evicted first, free to OOM its node), so the chart
    # supplies the numbers. Shape is the k8s `resources` block verbatim, e.g.
    # {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}}.
    runner_resources: dict[str, dict[str, str]] | None = None
    # --- model catalog (OME-625). The catalog endpoint forwards the CALLER's credential, so
    # there is deliberately NO credential setting here: url4-cloud holds no aigateway secret.
    # `aigateway_base_url` above is the only precondition for the feature.
    #
    # WHY a TTL at all: the catalog is a provider registry — it changes on deploy, not on traffic.
    models_cache_ttl_s: float = 300.0
    # WHY a ceiling on stale service: an outage should not empty every client's model list, but an
    # indefinitely stale catalog would advertise models that may since have been retired.
    models_cache_stale_max_s: float = 3600.0
    # WHY: single-flight collapses CONCURRENT misses; this bounds SEQUENTIAL retries so a warm
    # caller polling through an aigateway outage does not hit upstream on every request.
    models_cache_error_backoff_s: float = 30.0
    # INVARIANT: cache keys derive from credentials url4-cloud does not verify, so the entry count
    # must be bounded rather than left to the caller population (spec §7).
    models_cache_max_entries: int = 256
    # INVARIANT: distinct credentials bypass single-flight entirely, so this bulkhead is the only
    # thing bounding concurrent upstream catalog fetches. The apigw is the rate limiter in front;
    # this is the in-app backstop.
    models_upstream_concurrency: int = 8

    # INVARIANT: a finished Job's NAME is the stateless single-use replay guard, so reclaiming
    # it re-opens replay for that topic — but only for as long as the token is still usable.
    # See `effective_job_ttl_s` and `_reject_replayable_job_ttl`. None => derive the floor.
    job_ttl_s: int | None = None

    @property
    def effective_job_ttl_s(self) -> int:
        """Seconds a finished Runner Job is retained before k8s reclaims it.

        ``ttlSecondsAfterFinished`` counts from the moment the Job FINISHES, and the Job object
        exists for the whole run already — so the only gap the guard must cover is the interval
        after completion in which the starting token could still be presented again. A token
        carries ``exp = iat + iat_window_s`` (:meth:`JwtCodec.mint`), so it is rejected at auth,
        before ``exists()`` is ever consulted, once that window passes. ``iat_window_s`` is
        therefore the true floor; the extra :data:`_TTL_SKEW_MARGIN_S` only absorbs clock skew
        between the App validating ``exp`` and the k8s TTL controller doing the deletion.

        AIDEV-NOTE: this used to derive ``iat_window_s + job_deadline_s``, which conflated two
        different clocks — ``job_deadline_s`` measures a RUN, not the post-completion replay
        gap. At the 16 h default that retained ~960x more Job/Pod objects than the guard needs
        (~14 KB of etcd per request, held for 16 h), which is the scaling ceiling of this design
        rather than a property of it. Do not reintroduce the ``job_deadline_s`` term.
        """
        if self.job_ttl_s is not None:
            return self.job_ttl_s
        return self.iat_window_s + _TTL_SKEW_MARGIN_S

    @model_validator(mode="after")
    def _reject_replayable_job_ttl(self) -> Self:
        """INVARIANT: an explicit ``job_ttl_s`` may never drop below the token's own lifetime.

        Reclaiming the Job deletes the name that makes a replayed token fail with 409. Below
        ``iat_window_s`` that deletion can happen while the token is still within its ``exp``,
        opening a window for an already-spent token to start a second run. Raising it is
        legitimate (keeping failures around for post-mortem); dropping below the floor is a
        security regression, and is refused at startup rather than on the first replay.
        """
        if self.job_ttl_s is not None and self.job_ttl_s < self.iat_window_s:
            raise ValueError(
                f"job_ttl_s={self.job_ttl_s} is below the replay floor {self.iat_window_s} "
                f"(iat_window_s, the token's own lifetime) — a Job reclaimed while its token is "
                f"still valid re-opens replay"
            )
        return self
