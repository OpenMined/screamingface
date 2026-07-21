# url4-cloud protocol

The wire contract for url4-cloud telemetry and control. It is deliberately built from **named,
public standards** rather than bespoke shapes, so any off-the-shelf client, tracing backend, or
API tool understands it. This document is the reference **and** the decision record: every layer
below names the standard it conforms to, links it, and states the rationale. The one place we
knowingly deviate (cost) is called out explicitly.

> Scope: the protocol is transport-agnostic. The **same messages** flow over the in-process
> `Channel`, over **NATS** (worker → app), and over the **WebSocket** (app → browser). Only the
> transport binding differs (§8); the message shape does not.

---

## 1. Message envelope — CloudEvents 1.0

**Decision:** every message is a **CloudEvents 1.0** event in *structured* content mode, media
type `application/cloudevents+json`.
**Why:** CloudEvents is the CNCF standard event envelope; it already standardizes the two
mechanisms we would otherwise invent — event *sequence* and *trace context* — as official
extensions. **Ref:** <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md>,
JSON format <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md>.

| Attribute | Requirement | url4-cloud usage |
|---|---|---|
| `specversion` | required | `"1.0"` |
| `id` | required | unique per event (ULID/UUID) — dedup identity |
| `source` | required | the emitting node, e.g. `/trace/<trace_id>/node/<node_id>` (URI-ref) |
| `type` | required | reverse-DNS, see §4 (`ai.url4.span`, `ai.url4.cost.usage`, …) |
| `time` | optional | RFC 3339 emit time |
| `subject` | optional | the run == `<trace_id>` |
| `datacontenttype` | optional | `application/json` |
| `dataschema` | optional | the JSON-Schema `$id` of the payload |
| `data` | — | the typed payload (§5) |

**Extensions (also standard CloudEvents):**
- **`sequence`** + `sequencetype: "Integer"` — monotonic per stream; the dedup/resume key.
  **Ref:** <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/extensions/sequence.md>.
- **`traceparent`** / `tracestate` (Distributed Tracing extension) — §3.
  **Ref:** <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/extensions/distributed-tracing.md>.

---

## 2. Transport model

One message model, three transports (spec §2.1). In-process = native objects (no serialization);
NATS + WebSocket = CloudEvents JSON. The app is a bridge, not a translator.

---

## 3. Trace context — W3C Trace Context

**Decision:** carry trace/span identity as a W3C **`traceparent`** string in the CloudEvents
Distributed-Tracing extension; `trace_id` (32 hex) and `span_id` (16 hex) are W3C-conformant.
**Why:** `traceparent` is the interop standard every tracer (OTel, Jaeger, Tempo, Datadog)
already parses. **Ref:** <https://www.w3.org/TR/trace-context/>.
`traceparent = 00-<32-hex trace-id>-<16-hex span-id>-<2-hex flags>`.

---

## 4. Message catalog (`type`)

Reverse-DNS per CloudEvents guidance. Outbound (engine/tool → app → client): `ai.url4.started`,
`ai.url4.log`, `ai.url4.span`, `ai.url4.cost.usage`, `ai.url4.heartbeat`, `ai.url4.result`,
`ai.url4.terminated`. Inbound (client → app → engine): `ai.url4.execute`, `ai.url4.stop`,
`ai.url4.attach`. The set is a **JSON-Schema `oneOf` discriminated on `type`** (OpenAPI/AsyncAPI
discriminator) — **Ref:** <https://spec.openapis.org/oas/v3.1.0#discriminator-object>.

---

## 5. Payloads (`data`)

### 5.1 `ai.url4.span` — OpenTelemetry GenAI
**Decision:** span `data` uses **OTel GenAI** semantic-convention keys verbatim.
**Why:** these are the emerging standard for LLM telemetry; using them verbatim makes the data
OTLP-exportable to any OTel backend (§9). **Status:** experimental — opt in with
`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
**Ref:** <https://opentelemetry.io/docs/specs/semconv/gen-ai/>.

| Field | OTel GenAI attribute |
|---|---|
| operation | `gen_ai.operation.name` |
| provider | `gen_ai.provider.name` |
| request/response model | `gen_ai.request.model` / `gen_ai.response.model` |
| input/output tokens | `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` |

Plus the OTel **Span** shape: `name`, `kind`, `start`/`end` (RFC 3339), `status`. **Tokens live
here; cost does NOT** (§5.3).

### 5.2 `ai.url4.log` — OTel Logs Data Model
**Decision:** log `data` follows the **OTel Logs Data Model**: `SeverityNumber` (DEBUG=5, INFO=9,
WARN=13, ERROR=17) + `SeverityText`, `Body`, `Attributes`.
**Ref:** <https://opentelemetry.io/docs/specs/otel/logs/data-model/>.

### 5.3 `ai.url4.cost.usage` — custom event (conscious deviation)
**Decision:** cost is a **separate event**, never a span attribute. There is **no ratified cost
standard** — OTel deliberately excludes cost from spans because it is *derived* (tokens ×
pricing). We therefore keep a custom `type`, but: token counts reuse `gen_ai.usage.*`, money is a
`Decimal` serialized as a **string** (JSON has no decimal), `total_usd == Σ parts` (enforced),
and `scope ∈ {self, subtree}` with `subtree == self + Σ children.subtree`.
**Prior art (not a standard):** Langfuse `costDetails`, OpenLLMetry; OTel GenAI *metrics*
(`gen_ai.client.token.usage`) for token aggregates.
**Ref:** <https://langfuse.com/docs/model-usage-and-cost>,
<https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/>.

### 5.4 lifecycle — `started` / `heartbeat` / `result` / `terminated`
Plain typed payloads. `terminated.error` mirrors url4 `Url4Error` (`code`, `message`,
`permanent`) so Guard semantics survive across the wire. `terminated.status ∈ {succeeded,
failed, stopped, timed_out}`.

---

## 6. Sequencing & resume — CloudEvents `sequence` + SSE `Last-Event-ID`
**Decision:** the CloudEvents `sequence` is the dedup + resume key; a reconnecting client sends
`ai.url4.attach` with `from_sequence` and the app replays the gap then goes live — the exact
semantics of SSE `Last-Event-ID` / a JetStream stream sequence.
**Ref:** <https://html.spec.whatwg.org/multipage/server-sent-events.html>.

---

## 7. Control (REST) layer standards

| Concern | Standard | Ref |
|---|---|---|
| Errors (401/409/428/502/504) | **RFC 9457 Problem Details** — `application/problem+json` (`type`/`title`/`status`/`detail`/`instance`) | rfc-editor.org/rfc/rfc9457 |
| Sync vs async | **RFC 7240** `Prefer: respond-async` / `wait` + `Preference-Applied` | rfc-editor.org/rfc/rfc7240 |
| Async handle | **RFC 8288** `Link` + `Location` on the `202` | rfc-editor.org/rfc/rfc8288 |
| Token | **RFC 7519 (JWT)** registered claims — `sub` (topic), `iat`, **`exp`** (= iat+window), `iss`, `aud`, `jti` (replay id), HS256 | rfc-editor.org/rfc/rfc7519 |

**Note on JWT:** setting `exp` means *any* standard JWT library rejects an expired token for free;
our stateless `iat`-window check becomes belt-and-suspenders, not the sole guard.

---

## 8. Transport bindings — CloudEvents Protocol Bindings
**Decision:** use CloudEvents' own protocol bindings rather than a private framing.
- **WebSocket:** subprotocol `Sec-WebSocket-Protocol: cloudevents.json` (CloudEvents WebSocket
  binding), one CloudEvent per WS message.
  **Ref:** <https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/websockets-protocol-binding.md>.
- **NATS:** the CloudEvents NATS binding (subject routing + structured JSON).
  **Ref:** <https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/nats-protocol-binding.md>.

---

## 9. Observability & operations

| Concern | Standard | Ref |
|---|---|---|
| Telemetry export | Payloads use `gen_ai.*` + OTel Logs → **OTLP-exportable** to any OTel collector (dual-purpose: client stream + collector export) | opentelemetry.io |
| Metrics | **OpenMetrics/Prometheus** `/metrics`, exposing OTel GenAI metrics | github.com/OpenObservability/OpenMetrics |
| Health probes | **k8s convention** `/livez`, `/readyz` (+ `/healthz`) | kubernetes.io probes |
| k8s labels | **recommended labels** `app.kubernetes.io/*` | kubernetes.io common-labels |
| Container image | **OCI annotations** `org.opencontainers.image.*` | opencontainers/image-spec |

---

## 10. Decision log (summary)

| # | Layer | Standard | Status |
|---|---|---|---|
| D1 | Envelope | CloudEvents 1.0 (structured, `application/cloudevents+json`) | adopt |
| D2 | Sequence/resume | CloudEvents `sequence` + SSE `Last-Event-ID` | adopt |
| D3 | Trace context | W3C Trace Context (`traceparent`) via CE Distributed-Tracing ext | adopt |
| D4 | Spans | OTel GenAI `gen_ai.*` (experimental, opt-in) | adopt |
| D5 | Logs | OTel Logs Data Model | adopt |
| D6 | Cost | custom `ai.url4.cost.usage` — **no standard exists** (prior art Langfuse/OTel metrics) | **deviate (documented)** |
| D7 | Message typing | JSON-Schema `oneOf` + discriminator | adopt |
| D8 | REST errors | RFC 9457 Problem Details | adopt |
| D9 | Sync/async | RFC 7240 Prefer + RFC 8288 Link | adopt |
| D10 | Token | RFC 7519 JWT registered claims (+ `exp`) | adopt |
| D11 | Transport bindings | CloudEvents WebSocket + NATS bindings | adopt |
| D12 | Metrics / health / labels | OpenMetrics · k8s probes · k8s+OCI labels | adopt |

---

## 11. Example — `ai.url4.cost.usage` (structured CloudEvent)

```json
{
  "specversion": "1.0",
  "id": "01J9Z8Q7C6K3M2E4T5V6W7X8Y9",
  "source": "/trace/9f2c.../node/root",
  "type": "ai.url4.cost.usage",
  "subject": "9f2c...",
  "time": "2026-07-21T09:00:03Z",
  "datacontenttype": "application/json",
  "sequence": "7",
  "sequencetype": "Integer",
  "traceparent": "00-9f2c1e0000000000aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
  "data": {
    "scope": "self",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.response.model": "claude-opus-4-8",
    "pricing_version": "2026-07-01",
    "usage": { "gen_ai.usage.input_tokens": 1200, "gen_ai.usage.output_tokens": 340 },
    "cost": { "input_usd": "0.0180", "output_usd": "0.0255", "total_usd": "0.0435" }
  }
}
```

---

*The `url4_streaming_protocol` Pydantic models (OME-526 follow-on) implement exactly this; spec §7 is
updated to match. Where a standard is experimental (D4) or absent (D6), that is stated above, not
hidden.*
