"""Every env var a Runner Job reads, and which side supplies it.

One image runs both modes now (`url4-cloud serve` / `url4-cloud run`), so this is a single
module rather than the two hand-synced copies it replaces. Two sources feed a Job's
environment, and the run mode cannot tell them apart — it just reads its environment:

- PER-RUN, written by the App onto the Job spec (:data:`WRITTEN_BY_APP`). None of it exists
  until a request arrives, which is exactly why Helm cannot supply it.
- PER-DEPLOY, named AND valued by the Helm chart and injected wholesale with ``envFrom``
  (:data:`DEPLOY_TIME`). The App never writes these — the chart is the only writer, so there is
  nothing to keep in sync.

These names are url4-cloud's, not the engine's: half are aigateway-specific and the rest
describe how this app schedules a run. None of it is part of the url4 language or its wire
format.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

# --- per-run: written by the App onto the Job spec -------------------------------------------
TOPIC = "URL4_CLOUD_TOPIC"
EXPRESSION = "URL4_CLOUD_EXPRESSION"
JOB_DEADLINE_S = "URL4_CLOUD_JOB_DEADLINE_S"
TRACEPARENT = "URL4_CLOUD_TRACEPARENT"

AIGATEWAY_PROFILE = "AIGATEWAY_PROFILE"
"""Per-request profile selection; absent means the gateway's default.

Orthogonal to identity: it selects WHICH of the resolved account's stored credentials to use, not
who the caller is, so it is forwarded on its own merits.
"""

IDENTITY_HEADER_ENV: Mapping[str, str] = MappingProxyType(
    {
        "X-User-Email": "URL4_CLOUD_IDENTITY_USER_EMAIL",
    }
)
"""The caller's VERIFIED identity, and the env name it travels under.

https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/ — Cloudflare Access
authenticates the caller at the edge, and Envoy re-verifies that assertion against Cloudflare's
JWKS before clearing any client-supplied copy of this header and re-injecting it from the verified
claims. By the time it reaches the App it is trustworthy and a client cannot forge it.

WHY only the email: aigateway keys a caller's account on it, and an email is globally unique — so
the flow's tenant header adds nothing to a key built from it. Cloudflare service tokens (which carry
a `common_name` and no email) are out of scope until the gateway issues its own API keys, so
automation is not identified here at all rather than half-identified.

INVARIANT: this table is the ONLY place the header↔env correspondence is written. Both adapters
render a Job's env from it and the run mode reads its env back through it, so a header added here
reaches aigateway without touching either half.

WHY plain env and not a Secret: this is identity, not a credential — it authorizes nothing on its
own, and a Secret would imply a confidentiality it does not have. The accepted cost is that
``get jobs`` RBAC reveals the caller's email.

INVARIANT: this is now the ONLY thing url4-cloud forwards about a caller. aigateway runs either
``cloudflare_headers`` (deployed — reads this header) or ``disabled`` (local — anonymous). Neither
reads ``Authorization``, so no bearer token is carried anywhere in this app.
"""


def identity_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """The identity headers present on an inbound request, canonical name → value.

    ``headers`` must look up case-insensitively (Starlette's ``Headers`` does); HTTP header names
    are case-insensitive on the wire, but the value returned here is keyed by the canonical casing
    so the outgoing request renders one spelling regardless of what arrived.

    A present-but-blank header is dropped: it carries no identity, and forwarding it would let a
    downstream reader see the header and conclude the caller is of that kind.
    """
    return {
        header: stripped
        for header in IDENTITY_HEADER_ENV
        if (stripped := (headers.get(header) or "").strip())
    }


def identity_to_env(identity: Mapping[str, str]) -> dict[str, str]:
    """Render an identity mapping as the Job env keys that carry it. Unknown headers are dropped."""
    return {
        IDENTITY_HEADER_ENV[header]: value
        for header, value in identity.items()
        if value and header in IDENTITY_HEADER_ENV
    }


def identity_from_env(env: Mapping[str, str]) -> dict[str, str]:
    """Read an identity mapping back out of a run's environment, canonical header name → value."""
    return {
        header: stripped
        for header, name in IDENTITY_HEADER_ENV.items()
        if (stripped := (env.get(name) or "").strip())
    }


# --- per-deploy: named by the chart, injected via envFrom ------------------------------------
NATS_URL = "URL4_CLOUD_NATS_URL"
AIGATEWAY_BASE_URL = "AIGATEWAY_BASE_URL"

AIGATEWAY_MODEL = "AIGATEWAY_MODEL"
"""Overrides the default route declared in the image's `url4.toml` (`config.aigatewayModel`)."""

TAVILY_API_KEY = "TAVILY_API_KEY"
"""Injected from the Tavily Secret by `envFrom`, so the Secret's KEY must be this exact name.
Absent => web tools stay off."""

RUNNER_CONFIG = "URL4_RUNNER_CONFIG"
"""Path to the declared world (:mod:`url4_cloud.runner.config`). Baked into the image; the App
never writes it."""

DEFAULT_NATS_URL = "nats://localhost:4222"
"""Fallback for an unset :data:`NATS_URL`. Lives beside the name it defaults so the two cannot
drift — every reader of the variable needs the same answer for "and if it is absent?"."""

# --- the sets the adapters and their tests are keyed off -------------------------------------
SECRET: frozenset[str] = frozenset()
"""Values that must NEVER appear literally in a Job spec.

A Job object is not a secret store — it is readable with ``get jobs`` RBAC alone, echoed by
``kubectl describe``/``-o yaml``, and captured in the create-call audit log. Anything listed here
must travel by reference (``valueFrom.secretKeyRef``); `test_job_env_contract.py` pins that, keyed
off this set.

Currently EMPTY, and that is the point: the caller's bearer token was the only member, and no run
carries one any more (see :data:`IDENTITY_HEADER_ENV`). The set stays so the contract test keeps
holding — re-adding a per-run secret must go through it rather than around it.
"""

REQUIRED = frozenset({TOPIC, EXPRESSION})
"""Absent ⇒ run mode raises ``RunnerConfigError`` at boot. Every adapter must write these."""

WRITTEN_BY_APP = frozenset(
    {
        TOPIC,
        EXPRESSION,
        JOB_DEADLINE_S,
        TRACEPARENT,
        AIGATEWAY_PROFILE,
        *IDENTITY_HEADER_ENV.values(),
    }
)
"""The per-run subset. A key the App writes that is NOT in here reaches nothing — the direction
that breaks silently is an unread WRITE, not an unwritten READ (which simply falls back)."""

DEPLOY_TIME = frozenset(
    {NATS_URL, AIGATEWAY_BASE_URL, AIGATEWAY_MODEL, TAVILY_API_KEY, RUNNER_CONFIG}
)
"""Helm owns these end-to-end. The App writing one would make it two sources of truth again."""

__all__ = [
    "AIGATEWAY_BASE_URL",
    "AIGATEWAY_MODEL",
    "AIGATEWAY_PROFILE",
    "DEFAULT_NATS_URL",
    "DEPLOY_TIME",
    "EXPRESSION",
    "IDENTITY_HEADER_ENV",
    "JOB_DEADLINE_S",
    "NATS_URL",
    "REQUIRED",
    "RUNNER_CONFIG",
    "SECRET",
    "TAVILY_API_KEY",
    "TOPIC",
    "TRACEPARENT",
    "WRITTEN_BY_APP",
    "identity_from_env",
    "identity_from_headers",
    "identity_to_env",
]
