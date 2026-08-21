# OME-692 — Show authoritative live cache progress (spec)

Status: approved for implementation on 2026-08-21 as a Client-only increment of the broader
blocked issue.

## Outcome

While `sf.evaluate(...)` is running, its notebook panel shows an authoritative cache hit rate and
the observed hit, miss, and bypass counts after the cost cell. Public `sf.events.Span` values retain
the Engine's `cache_status` and `cache_reason` so callbacks can inspect the same evidence.

## Contract

- `Span.cache_status` is `"hit"`, `"miss"`, `"bypass"`, or `None`.
- `Span.cache_reason` is a non-blank string or `None`; the Client preserves the Engine vocabulary
  without interpreting it.
- Unknown or absent provenance remains `None`. The Client never infers cache behavior from latency,
  tokens, cost, or model identity.
- Each cache-bearing model Span increments that Run's live count exactly once.
- An Engine cache-summary Log replaces that Run's live count. It is the authoritative final
  reconciliation and is not added to the Span-derived count.
- Evaluation totals sum the latest authoritative count for every Candidate Run.
- Hit rate is `hits / (hits + misses)`. Bypasses are displayed but excluded from the denominator.
  With no hit or miss evidence, the rate is unavailable rather than zero.

## Presentation

The Evaluation panel gains one square, hairline stat cell after Cost:

- label: `cache hit rate`;
- primary value: percentage to one decimal place, or an em dash when unavailable;
- receipt: pluralized hit, miss, and bypass counts when provenance is available.

The four-cell row follows the existing ScreamingFace app-register visual system: Plex Mono for
labels and figures, semantic existing tokens only, square geometry, no new colour or decoration,
and a one-column mobile layout.

## Non-goals

- Computing or displaying saved money.
- Cache keys, writes, or age not present in the current Engine Span contract.
- Client-owned cache lookup, mutation, or fingerprinting.
- Benchmark-specific cache rules.
- Closing the broader `OME-692` issue while its saved-accounting dependency remains unfinished.

## Acceptance

1. Decoding a cache-bearing Engine Span preserves status and reason in `sf.events.Span`.
2. Invalid status or blank reason fails the existing strict Event contract.
3. Live Spans update hit, miss, bypass, and hit rate immediately.
4. A final summary replaces, rather than doubles, the live counts for its Run.
5. Multiple Candidate Runs aggregate without one Run overwriting another.
6. No provenance renders an unavailable cache metric, not a fabricated zero.
7. Existing progress, cost, tokens, completion, and text-summary behavior remains intact.

