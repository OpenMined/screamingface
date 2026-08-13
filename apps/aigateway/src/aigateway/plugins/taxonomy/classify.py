"""Core-owned, provider-neutral outcome and failure classification (OME-303 §7 U7).

INVARIANT (§9.20): ``conversion_error`` — and every other outcome — is decided HERE, by
core, from provider-neutral facts. Core may not import a plugin (repo architecture rule),
so an OpenRouter or Anthropic classifier can never become the definition of what these
words mean. A provider mapper reports EVIDENCE; it does not name the outcome.

INVARIANT: ``failure_code`` values come from a CLOSED vocabulary. Raw provider text,
prompts, headers, credentials and tracebacks never reach a record — a provider error
message is attacker-influenced and would be published straight into the response.
"""

from __future__ import annotations

from typing import Final

from ...core.http_status import valid_http_status
from .types import CallOutcome

__all__ = [
    "FAILURE_CODES",
    "classify_conversion_failure",
    "classify_transport_failure",
    "outcome_for_status",
]

# The closed sanitized failure vocabulary. Adding a member is a contract change.
FAILURE_CODES: Final[frozenset[str]] = frozenset(
    {
        "provider_status_error",
        "transport_connect_error",
        "transport_read_error",
        "transport_timeout",
        "transport_error",
        "response_conversion_failed",
        "no_response_observed",
    }
)


def outcome_for_status(status: object) -> CallOutcome:
    """Outcome implied by a validated HTTP status alone.

    A send that produced no validatable status produced no proof of what happened to
    it: it may have been received and billed, or never have arrived. That is
    ``indeterminate``, not success and not failure.
    """
    validated = valid_http_status(status)
    if validated is None:
        return "indeterminate"
    if 200 <= validated < 300:
        return "succeeded"
    return "provider_error"


def classify_transport_failure(exc: BaseException) -> tuple[CallOutcome, str]:
    """Map a local send failure to ``(outcome, failure_code)`` by exception TYPE only.

    WHY type and not message: an exception's ``str()`` carries provider- and
    network-controlled text, and this value is published in the response.

    AIDEV-NOTE: httpx is imported lazily so this module stays importable in contexts
    that never touch the transport. The names are matched structurally rather than with
    ``isinstance`` chains against a long import list, so an httpx version that adds a
    subclass still lands in the right bucket.
    """
    name = type(exc).__name__
    if "Timeout" in name:
        return "transport_error", "transport_timeout"
    if "Connect" in name:
        return "transport_error", "transport_connect_error"
    if "Read" in name or "RemoteProtocol" in name:
        return "transport_error", "transport_read_error"
    return "transport_error", "transport_error"


def classify_conversion_failure() -> tuple[CallOutcome, str]:
    """The outcome for "the provider answered, but local conversion failed".

    INVARIANT: this is NOT a transport error and NOT a provider error. The provider
    already produced — and very likely billed — a response; only the gateway's own
    conversion of it failed. Collapsing it into ``provider_error`` would tell Engine the
    provider rejected work it actually performed.
    """
    return "conversion_error", "response_conversion_failed"
