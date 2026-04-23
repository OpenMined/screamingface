"""Session enrichment + save helpers used by ``proxy_messages``.

The proxy sits between Claude Code and Anthropic. When a per-session
proxy is active, these helpers run two ends of the request lifecycle:

- Before forwarding: :meth:`SessionHook.enrich` calls the
  ``session.enrich_request`` hook, which may rewrite the request body
  (typically to prepend prior conversation turns from session state).
- After the upstream response: :meth:`SessionHook.save` calls the
  ``session.save_response`` hook to persist the new user/assistant
  turn back to session state.

Both are no-ops when no session-id or hook registry is configured.

Extracted from ``proxy.py`` during SF-107 so the hot ``proxy_messages``
handler stays focused on HTTP forwarding and url4 context injection,
not on session plumbing.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext as _nullcontext
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SessionHook:
    """Per-request session hook bundle.

    ``from_request`` builds one from the current request headers plus
    the plugin-level settings / hook registry; if any required piece
    is missing, :attr:`enabled` is ``False`` and ``enrich``/``save``
    become no-ops.
    """

    session_id: str | None
    service_url: str | None
    hooks: Any
    # Snapshot of the last user message taken at enrich time so save()
    # can pair it with the assistant response when persisting the turn.
    original_user_msg: dict | None = None

    @classmethod
    def from_request(
        cls,
        *,
        session_id: str | None,
        service_url: str | None,
        hooks: Any,
    ) -> SessionHook:
        return cls(session_id=session_id, service_url=service_url, hooks=hooks)

    @property
    def enabled(self) -> bool:
        return bool(self.session_id and self.service_url and self.hooks)

    async def enrich(self, body: dict[str, Any], *, tracer: Any = None) -> dict[str, Any]:
        """Emit ``session.enrich_request`` and apply any hook-returned body.

        Also snapshots the last user message so :meth:`save` has
        something to pair with the assistant response.

        Returns the (possibly modified) body — never None.
        """
        if not self.enabled:
            return body

        msgs = body.get("messages", [])
        if msgs:
            last = msgs[-1]
            self.original_user_msg = last.copy() if isinstance(last, dict) else last

        enrich_ctx = (
            tracer.start_as_current_span("session.enrich_request") if tracer else _nullcontext()
        )
        with enrich_ctx:
            _record_session_attrs(self.session_id, self.service_url)
            try:
                results = await self.hooks.emit_async(
                    "session.enrich_request",
                    body=body,
                    session_id=self.session_id,
                    session_service_url=self.service_url,
                )
                modified = False
                for result in results:
                    if result is not None:
                        body = result
                        modified = True
                        break
                _record_session_attrs(modified=modified)
            except (httpx.HTTPError, TimeoutError, ConnectionError) as exc:
                # Narrowed from the original bare ``except Exception`` —
                # transport-layer failures are expected; everything else
                # should bubble so we see bugs.
                logger.warning("Session enrichment failed for %s: %s", self.session_id, exc)

        return body

    async def save(
        self,
        response_data: dict[str, Any] | None,
        *,
        streaming: bool,
        tracer: Any = None,
    ) -> None:
        """Emit ``session.save_response`` for the completed turn."""
        if not self.enabled or response_data is None or self.original_user_msg is None:
            return

        save_ctx = (
            tracer.start_as_current_span("session.save_response") if tracer else _nullcontext()
        )
        with save_ctx:
            _record_session_attrs(self.session_id, self.service_url, streaming=streaming)
            try:
                await self.hooks.emit_async(
                    "session.save_response",
                    session_id=self.session_id,
                    session_service_url=self.service_url,
                    user_message_body=self.original_user_msg,
                    response_body=response_data,
                )
            except (httpx.HTTPError, TimeoutError, ConnectionError) as exc:
                logger.warning(
                    "Session save (%s) failed for %s: %s",
                    "stream" if streaming else "non-stream",
                    self.session_id,
                    exc,
                )


def _record_session_attrs(
    session_id: str | None = None,
    service_url: str | None = None,
    *,
    modified: bool | None = None,
    streaming: bool | None = None,
) -> None:
    """Record session-hook attributes on the current OTEL span, best-effort."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return
    if session_id is not None:
        span.set_attribute("session.id", session_id)
    if service_url is not None:
        span.set_attribute("session.service_url", service_url)
    if modified is not None:
        span.set_attribute("session.modified", modified)
    if streaming is not None:
        span.set_attribute("session.streaming", streaming)
