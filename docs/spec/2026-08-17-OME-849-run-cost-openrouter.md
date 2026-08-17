# OME-849 — Report real run cost from provider-authored OpenRouter evidence (spec)

Status: drafted 2026-08-17, awaiting owner approval to implement.
Sub-issues: `OME-850` (packages/url4) → `OME-851` (apps/url4-cloud). `OME-850` lands first.
Producer contract this consumes: `apps/aigateway/docs/usage-accounting.md` (`OME-303`, PR #567).

A run's Report shows `—` where a cost belongs. Everything except one link is already built. This
spec joins the chain for the OpenRouter case only.

## 0. Locked decisions (owner, 2026-08-17)

- **OpenRouter only.** No rate card in this epic.
- **1 `openrouter_credits` = 1 USD.**
- **Anthropic stays unpriced**, and a mixed-provider run reports `unpriced` for the whole run.
- **Cache status stays reported twice** — response headers *and* `_aigw`. Accepted duplication,
  explicitly not a defect to chase here.
- **Degrade to `unpriced`, never to `$0`.**

## 1. Why the chain is cut

`apps/url4-cloud/src/url4_cloud/runner/executor.py:313` and `:352` hardcode
`pricing_version="unpriced"` with `CostBreakdown(total_usd=Decimal("0"))`, and
`runner/connector.py:405` passes only the provider's own `usage` object to `_report_usage`,
discarding `_aigw` entirely.

The placeholder is **honest**: `packages/screamingface/.../_engine/contract.py:357,385` reads
`pricing_version == "unpriced"` and renders `cost_usd=None`, which `_ui/report_view.py:288` shows as
`—` titled "cost not reported by this run". Nobody is shown a wrong number today. **The single
largest risk in this epic is replacing a truthful dash with a confident wrong figure.** Every rule
below exists to prevent that.

## 2. `packages/url4` — two non-breaking widenings (`OME-850`)

### 2.1 `CostBreakdown` accepts a total without a breakdown

`streaming/protocol/taxonomy.py:47-58` enforces
`total_usd == Σ(input_usd, output_usd, cache_read_usd, cache_creation_usd, reasoning_usd)`, and every
component defaults to `Decimal("0")`. OpenRouter authors **one** amount with no per-class split, so
`CostBreakdown(total_usd=Decimal("0.001"))` raises. Today's `total_usd=Decimal("0")` validates only
because zero equals zero.

Normative rule: **the per-class components are an optional partial breakdown; `total_usd` is
authoritative.** The validator changes from equality to `Σ components <= total_usd`. Over-reporting
stays an error — a breakdown claiming more than the total is still incoherent — while an *incomplete*
breakdown becomes legal.

Rejected alternative: assigning the whole amount to `input_usd`. It validates and it writes a false
claim into a structured field that a future breakdown view will believe.

Precedent that this is the right direction: the consumer at the end of the chain was already built
for it. `_engine/contract.py:350` notices a total that disagrees with its components, logs a warning,
and uses `total_usd`. The strict validator in the middle is the outlier.

### 2.2 The `Usage` observation event carries the remaining cost facts

`observe.py:66-79` `Usage` carries only `input_tokens` and `output_tokens`. The wire protocol
(`TokenUsage`, `taxonomy.py:6-33`) already has five classes, so the observation seam is the narrow
part, and it is the **only** reliable channel: span attribution comes from the sink binding the
executor installs per node task (`dag/executor.py::_eval`), so a private url4-cloud side channel
could not attribute cost to the right span.

Add, all optional and defaulted so no existing caller changes:

```python
cache_read_tokens: int | None = None
cache_creation_tokens: int | None = None
reasoning_tokens: int | None = None
cost_usd: Decimal | None = None   # priced USD for this round trip; None means unpriced
```

`UsageSink` is already `Callable[..., None]` (`observe.py:150`), so the sink type needs no change, and
`ResponseSink`'s own comment (`observe.py:178-180`) records the precedent: optional kwargs were added
to this live seam before, precisely so an adapter that learns nothing can say nothing.

Two invariants on the new fields:

- **`None` means the provider did not say — never `0`.** This mirrors aigateway's own rule and the
  existing `response_model` invariant at `observe.py:76-78`. The pre-existing `input_tokens` /
  `output_tokens` stay non-optional `int`; widening them is a breaking change to a live seam and is
  not required, because incomplete evidence forces `cost_usd=None` anyway.
- **`cost_usd` is already USD.** Unit conversion happens in the adapter that understands the
  provider's contract, not here. `packages/url4` performs no arithmetic on it — it stays a carrier
  (`streaming/lifecycle.py` only copies and re-scopes).

## 3. `apps/url4-cloud` — read the accounting and price it (`OME-851`)

### 3.1 New module: `runner/accounting.py`

One seam, one public function, total over its input:

```python
PRICING_VERSION = "openrouter-credits-1usd"
UNPRICED = "unpriced"

def usd_from_aigw(aigw: object) -> Decimal | None:
    """USD for one gateway call, or None when the evidence cannot support a price."""
```

`Decimal("0")` and `None` are different answers and the return type keeps them apart:
`Decimal("0")` is "this call was genuinely free", `None` is "we do not know". Collapsing them is the
defect this signature exists to prevent.

The function is **total**: a missing, non-dict, or malformed `_aigw` returns `None`. It never raises,
because a provider call that already succeeded must not be turned into a run failure by accounting —
the same rule aigateway applies on its side of the boundary.

### 3.2 The normative decision table

Read `_aigw.request_economics`. aigateway populates `known_direct_cost_subtotals` **only** when its
capture was complete and nothing was omitted; it has already summed across retries and already
refuses to emit a total if any amount was unreadable. Do not re-walk `attempts[]` to compute money.

| `direct_cost_status` | further condition | result |
|---|---|---|
| `complete` | exactly one subtotal, `unit == "openrouter_credits"` | `Decimal(amount)` |
| `complete` | zero, several, or a non-credits unit | `None` |
| `not_applicable` | `usage_accounting.cache.status == "hit"` | `Decimal("0")` |
| `not_applicable` | anything else | `None` |
| `partial` | — | `None` |
| `unavailable` | — | `None` |
| absent / unrecognised | — | `None` |

Rows 3 and 4 are the dangerous pair: **both present an empty subtotal list and mean opposite
things.** A cache hit genuinely cost nothing this request; `accounting_not_supported` means a real
billed call the gateway could not observe. This is the same failure aigateway's own review named —
treating absence of observation as proof of absence.

`amount` is parsed with `Decimal(str(value))`, never `float`. The multi-unit and non-credits rows are
what keeps this honest when a second provider appears: an unrecognised unit degrades to `unpriced`
rather than being silently added to a dollar total.

### 3.3 Reporting it — `connector.py`

`_fetch_completion` already returns the response; `_json_or_raise` already parses it. At
`connector.py:405`, pass the accounting through the existing sink:

```python
_report_usage(spec.id, data.get("usage"), data.get("_aigw"))
```

`_report_usage` (`connector.py:298-306`) is rewritten to prefer `_aigw` and to fix three defects that
are wrong independently of pricing:

- **`provider` is guessed** by splitting the model id, defaulting to `"anthropic"`. Take
  `_aigw.usage_accounting.attempts[-1].provider`. Pricing keyed on a guessed provider is how a
  future non-OpenRouter call gets priced as OpenRouter.
- **`response_model` is never reported.** `observe.py:76-78` states the invariant — `None` means the
  provider did not say, never a copy of the request — yet `executor.py:286-287` assigns the requested
  model to *both* request and response model. Report `attempts[-1].response_model`, which for
  OpenRouter genuinely differs from what was asked for.
- **`usage.get("prompt_tokens", 0)`** turns a missing count into zero. Read the token classes from
  `attempts[-1].usage.{input,output}` (`total`, `cache_read`, `cache_write`, `reasoning`), preserving
  `null` as `None`. Keep the provider `usage` object as the fallback only when `_aigw` is absent, and
  in that case pass `cost_usd=None`.

Token classes map as: `input.total → input_tokens`, `output.total → output_tokens`,
`input.cache_read → cache_read_tokens`, `input.cache_write → cache_creation_tokens`,
`output.reasoning → reasoning_tokens`. **`input.uncached` is deliberately not carried** — it is
`total` minus the cache classes and the protocol has no slot for it.

Aggregating `attempts[]` for tokens: sum across attempts, and **do not skip failed attempts** — a
failed attempt may still carry provider-authored usage. `attempts[-1]` is used only for the
*identity* facts (provider, response model), which the terminal attempt owns.

### 3.4 Accumulating it — `executor.py`

`_SpanState.usage` is a positional `tuple[str, str, int, int]` read as `usage[2]` / `usage[3]`. Nine
fields make that untenable; replace it with a `@dataclass(frozen=True, slots=True)` value. This is a
local refactor with no wire effect.

Accumulation follows the rule already established at `executor.py:257-268` — **accumulate, never
assign**, because one span makes several gateway calls (the web-tools loop is the normal case) and
assigning once kept only the final round trip. That comment records the bug; the new fields inherit
the same rule.

Money accumulates with **poisoning**, at both levels:

- a span's cost is `None` if *any* of its calls reported `None`, else the `Decimal` sum;
- `build_subtree` (`executor.py:346-355`) is `None` if *any* contributing span was `None`.

Nullable token classes accumulate the same way: `None` + anything is `None`. One shared helper does
both so the rule cannot drift between call sites.

Emission, in `_finish` and `build_subtree`:

- priced → `pricing_version=PRICING_VERSION`, `cost=CostBreakdown(total_usd=<sum>)` with no
  components set (legal after §2.1);
- unpriced → `pricing_version=UNPRICED`, `cost=CostBreakdown(total_usd=Decimal("0"))`, exactly as
  today, because the SDK discards the number when the version says unpriced.

`TokenUsage` on the wire keeps non-optional `int` fields, so an unknown class serializes as `0`.
That is tolerable **only** because an unknown class forces `unpriced`, which makes the SDK null the
token fields too (`contract.py:361-380`). Widening the wire `TokenUsage` is out of scope; the
coupling is recorded here so nobody later prices a run while leaving a class unknown.

## 4. Test plan — risk-ranked, RED first

P0 cases are the two that produce a plausible wrong number rather than a visible failure.

**P0 — money invented from nothing**

1. A cache hit prices to `Decimal("0")` and is marked **priced**; the run reports `$0.00`.
2. `capture_status: "accounting_not_supported"` with zero attempts prices to `None` and reports
   `unpriced` — *not* `$0`. Distinguishes rows 3 and 4 of §3.2.
3. A `cache.reference` (`incurred_in_current_request: false`) never contributes to a price. Its
   historical usage must not reach `cost_usd`.
4. One unpriced span makes the whole subtree unpriced, even when every other span priced cleanly.

**P1 — cardinality**

5. Two attempts in one `_aigw`, both `reported` → aigateway's single subtotal is used once, not
   summed twice from `attempts[]`.
6. A failed attempt carrying usage contributes its tokens and is not dropped.
7. Several gateway calls in one span (the web-tools loop) accumulate; the per-span cost equals their
   sum and reconciles against the subtree total.
8. `_fetch_completion`'s revalidation double-POST contributes exactly once. This is only correct
   because the discarded response was a cache hit — pin it, since the function's own comment names
   double-billing as the error class it exists to prevent.

**P1 — boundaries and hostile input**

9. `direct_cost_status: "partial"` → `unpriced`.
10. Two subtotals, or one whose `unit` is not `openrouter_credits` → `unpriced`.
11. `_aigw` absent, `None`, a non-dict, or structurally malformed → `unpriced`, no exception, and the
    provider response still succeeds.
12. An amount at the contract's precision bound (18 integer / 33 fractional digits) survives as an
    exact `Decimal`; a non-canonical or negative amount → `unpriced`.
13. `usage.status: "partial"` with a `null` token class → `unpriced`, and the class is `None` rather
    than `0` at the observation seam.

**P1 — the fixed defects**

14. `provider` comes from `_aigw`, not from splitting the model id — a bare model id no longer
    reports `"anthropic"`.
15. `response_model` differs from `requested_model` and both reach the span frame.

**P2 — regression guards (must pass before and after)**

16. An Anthropic-only run still reports `unpriced` and the Report still shows `—`.
17. A run with no model call at all emits no cost frame, exactly as today.
18. `CostBreakdown` with a full, exactly-matching breakdown still validates; components exceeding
    the total are still rejected.

**Not covered, deliberately:** live provider calls; streaming (no `_aigw` exists there); any
Anthropic price; leaderboard submission. Residual risk: the 1 credit = 1 USD constant is an owner
assertion, not something the code can verify.

## 5. Don't regress

- Accumulate-don't-assign for per-span usage (`executor.py:257-268`) — the bug it fixed made per-node
  cost under-report while the subtree stayed correct.
- A span id the run never opened is dropped, never fabricated (`executor.py:208-220`); run-level
  counters still count before the span guard (`executor.py:229-233`).
- Accounting never fails a completed provider response.
- `packages/url4` performs no cost arithmetic — it stays a carrier.
- The response-cache body is untouched; `_aigw` is read from the returned copy only.
- `pricing_version` remains the single switch the SDK reads to decide dash-versus-number.

## 6. Leaving room for a rate card

`pricing_version` names the *method*, so a second method is additive rather than a rewrite:

| value | meaning |
|---|---|
| `unpriced` | unknown — the SDK shows `—` |
| `openrouter-credits-1usd` | provider authored the amount; 1 credit = 1 USD |
| `ratecard-<date>` | tokens × a dated price list (future, not this epic) |

`usd_from_aigw` is the whole seam. A rate card becomes a second branch inside it when Anthropic needs
pricing. **No plugin, no registry, no port with one implementation, and no cost store** — persistence
belongs to the SDK and the scoreboard, which is the boundary aigateway drew.

## 7. Open questions

1. **Mixed-provider runs.** §0 locks "whole run unpriced". If mixed OpenRouter + Anthropic ensembles
   are routine, the alternative is a partial total plus an explicit incompleteness marker — which
   needs a new wire field and a Report affordance, so it is a separate unit either way.
2. **When to pin the method for a long run.** Moot while `openrouter-credits-1usd` is a constant;
   it becomes real with the first dated rate card, and a run can outlive a rate change.
