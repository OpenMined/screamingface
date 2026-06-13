"""Optional OTel HTTP-client tracing helpers for backend plugins.

All functions are no-ops when opentelemetry is not installed, so backend
modules can call them unconditionally. Mirrors
``url4_executor/_tracing.py`` but parametrized by provider so each span
carries the real provider identity (Anthropic, gemini, ollama, aigw, …).

Lives in ``llm_base`` (the lowest backend layer) on purpose: ``frontend_base``
already imports ``llm_base.constants``, so ``llm_base`` must not depend on
``frontend_base``. ``aigw_base`` already depends on ``llm_base`` and reuses
these helpers.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any

_TRACER_NAME = "screamingface.llm-base"


def _get_tracer():  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        return trace.get_tracer(_TRACER_NAME)
    except ImportError:
        return None


@contextmanager
def traced_provider_post(provider: str, url: str, *, method: str = "POST"):  # type: ignore[no-untyped-def]
    """Open a CLIENT span ``llm.{method} {provider}`` for an outbound POST.

    Yields the span (or ``None`` without OTel) so callers can record
    response attributes via :func:`set_provider_attrs`. Exceptions raised
    inside the ``with`` are recorded on the span by OTel on context exit.
    """
    tracer = _get_tracer()
    if tracer is None:
        with nullcontext() as span:
            yield span
        return
    from opentelemetry.trace import SpanKind

    with tracer.start_as_current_span(f"llm.{method} {provider}", kind=SpanKind.CLIENT) as span:
        if span.is_recording():
            span.set_attribute("sf.plugin", provider)
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", url[:500])
        yield span


def set_provider_attrs(attrs: dict[str, Any], span: Any = None) -> None:
    """Set attributes on the current (or provided) span; no-op without OTel.

    ``None`` values are skipped — OTel rejects ``None`` attribute values.
    """
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
            for k, v in attrs.items():
                if v is not None:
                    span.set_attribute(k, v)
    except ImportError:
        pass


_IO_CAP = 16000


def _cap(text: str) -> str:
    return text if len(text) <= _IO_CAP else text[:_IO_CAP] + f"… ({len(text) - _IO_CAP} more)"


def _extract_tokens(data: object) -> tuple[int | None, int | None]:
    """Best-effort prompt/completion token counts across provider response shapes."""
    if not isinstance(data, dict):
        return None, None
    usage = data.get("usage")
    if isinstance(usage, dict):
        # OpenAI/gateway: prompt_tokens/completion_tokens; Anthropic: input/output_tokens.
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        if prompt is not None or completion is not None:
            return prompt, completion
    meta = data.get("usageMetadata")  # Gemini
    if isinstance(meta, dict):
        return meta.get("promptTokenCount"), meta.get("candidatesTokenCount")
    return None, None


def record_llm_call(
    provider: str,
    request_body: dict | None,
    response: object,
    *,
    span: Any = None,
) -> None:
    """Set LLM input/output/model/tokens from a request body + httpx.Response.

    Provider-agnostic: serializes the request body as the input, the raw
    response text as the output, and extracts token usage from common response
    shapes. Best-effort and exception-safe; no-op without OTel.
    """
    import json

    output_value: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    try:
        output_value = _cap(response.text)  # type: ignore[attr-defined]
        prompt_tokens, completion_tokens = _extract_tokens(response.json())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — tracing must never break the request path
        pass
    try:
        input_value = _cap(json.dumps(request_body, default=str)) if request_body else None
    except (TypeError, ValueError):
        input_value = None
    set_llm_io(
        provider=provider,
        input_value=input_value,
        output_value=output_value,
        model=(request_body or {}).get("model"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        span=span,
    )


def set_llm_io(
    *,
    provider: str | None = None,
    input_value: str | None = None,
    output_value: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    span: Any = None,
) -> None:
    """Mark the current span as an OpenInference LLM call with input/output/model.

    Classifies the span ``openinference.span.kind = "LLM"`` (so Phoenix renders
    it as a model call) and records the request body / response / model / token
    counts. Call this only for actual model calls — generic transport spans
    (e.g. gateway auth-status GETs) must not be tagged LLM. ``None`` fields are
    skipped; no-op without OTel.
    """
    set_provider_attrs(
        {
            "openinference.span.kind": "LLM",
            "llm.provider": provider,
            "input.value": input_value,
            "input.mime_type": "application/json" if input_value else None,
            "output.value": output_value,
            "output.mime_type": "application/json" if output_value else None,
            "llm.model_name": model,
            "llm.token_count.prompt": prompt_tokens,
            "llm.token_count.completion": completion_tokens,
        },
        span=span,
    )
