"""OME-303 — AIGateway per-provider-attempt usage accounting.

FEATURE: an opt-in, provider-extensible EVIDENCE contract. A caller sending
``X-AIGW-Accounting: v1`` receives two sibling response-only objects under ``_aigw``:

* ``usage_accounting`` — one attempt per local provider HTTP send-pipeline admission,
  with token/cache/reasoning evidence and provider-authored cost; and
* ``request_economics`` — a current-request summary of known provider-authored cost.

STORY: as a benchmark operator I want bounded provider-authored usage and cost evidence
for every locally observed attempt, including retries, without the gateway guessing at
prices, provider receipt, execution or billing.

INVARIANT (the scope boundary): AIGateway returns FACTS. USD conversion, deterministic
attribution, run rollups, saved-cost persistence and UI belong to URL4/Engine. Nothing
here writes to a database, and no accounting metadata ever enters
``request_cache_entries.response_json``.

AIDEV-NOTE: the two halves are deliberately separate. CARDINALITY (how many sends
happened) is captured once for every LiteLLM-backed provider by the shared transport
observer in ``_handler``; SEMANTICS (what the provider's response means) come from
per-provider pure mappers. Adding a provider must never require touching the route, the
cache or the transport — only a capability declaration, a mapper and a cardinality test.
"""

from __future__ import annotations

# AIDEV-NOTE: ``_handler`` is deliberately NOT re-exported here — it imports litellm,
# and ``core.plugin_base`` imports this package. ``_collector`` is stdlib-only, so the
# request-scoped observation surface is safe to expose.
from ._collector import (
    RequestAccountingCollector,
    active_collector,
    bound_collector,
    new_gateway_call_id,
)
from ._money import canonical_amount, sum_amounts
from ._types import (
    SCHEMA_PROVIDER_ATTEMPT,
    SCHEMA_REQUEST_ECONOMICS,
    SCHEMA_USAGE_ACCOUNTING,
    TRANSPORT_LITELLM_ASYNC_HTTP_V1,
    AccountingCapability,
    CacheReference,
    CacheWriteTTL,
    CallOutcome,
    CaptureStatus,
    DirectCost,
    DirectCostStatus,
    InputTokenUsage,
    OutputTokenUsage,
    PricingContext,
    ProviderAttemptRecord,
    ProviderExtension,
    ProviderExtensionFact,
    ProviderUsageAccountingEvidence,
    TokenUsage,
    UsageAccountingStrategy,
    UsageSource,
)

__all__ = [
    "SCHEMA_PROVIDER_ATTEMPT",
    "SCHEMA_REQUEST_ECONOMICS",
    "SCHEMA_USAGE_ACCOUNTING",
    "TRANSPORT_LITELLM_ASYNC_HTTP_V1",
    "AccountingCapability",
    "CacheReference",
    "CacheWriteTTL",
    "CallOutcome",
    "CaptureStatus",
    "DirectCost",
    "DirectCostStatus",
    "InputTokenUsage",
    "OutputTokenUsage",
    "PricingContext",
    "ProviderAttemptRecord",
    "ProviderExtension",
    "ProviderExtensionFact",
    "ProviderUsageAccountingEvidence",
    "RequestAccountingCollector",
    "TokenUsage",
    "UsageAccountingStrategy",
    "UsageSource",
    "active_collector",
    "bound_collector",
    "canonical_amount",
    "new_gateway_call_id",
    "sum_amounts",
]
