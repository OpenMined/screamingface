---
ticket: UNFILED
stack: url4-cloud
status: in_progress
started: 2026-08-05
finished:
---

# UNFILED — spec: per-run cache policy for url4-cloud → aigateway

## PROCESS DEVIATION

**No Linear issue backs this unit.** The Linear MCP plugin is installed but unauthenticated;
`.claude/task-board.local.md` names it the ONLY permitted transport. Fourth occurrence this
session; the owner previously chose "proceed and record the deviation" for the identical
situation (`OME-743`, reconciled after the fact).

Back-fill once MCP is up: ledger `ticket:`/filename, branch name (`url4-cloud-cache-policy-spec`
→ `OME-N-<desc>`), `docs/tasks/` mirror, commit `Refs:`.

## Intent

Owner asked to plan the protocol change that lets a caller declare a run must not use
aigateway's response cache, and to produce a file to review before implementation.

Per CLAUDE.md rule 3 the artifact is a **spec** in `docs/spec/`, not a plan: this changes
url4-cloud's public REST contract. **No code in this unit.**

## What the investigation established (all verified against `main`)

1. **aigateway's cache is opt-in.** `routes/chat_dispatch.py:191` —
   `if not controls.use_cache: return None, "bypass", "not_requested"`. Controls arrive as a
   `cache` object in the request body (`core/request_cache/keys.py:71`), popped before provider
   plugins ever see it.
2. **url4-cloud can never send it.** `runner/connector.py:337` builds the body literally as
   `json={"model": model, "messages": messages, **extra}`, where `extra` is only
   `{tools, tool_choice}`. There is no `cache` field and no path to inject one.
3. **So every url4 run already bypasses**, with reason `not_requested`. A pure "turn caching
   off" switch would be a no-op on every code path — the inversion that reshapes the design.
4. **The response evidence is dropped too.** aigateway sets `X-AIGW-Cache`,
   `X-AIGW-Cache-Reason`, `X-AIGW-Cache-Key` (`chat_dispatch.py:218-226`); the connector reads
   the body only, so a hit would bill as a fresh call.
5. **The WS carries only `attach`/`stop` today** (`ws/bridge.py:57-67`;
   `protocol/unions.py:81` — `InboundFrame = StopEvent | AttachEvent`), and `GET /` *requires*
   an attached subscriber before it starts a run (`rest/routes.py:363`).

   **r1 read this as "the WS is the wrong carrier"** — arguing a pre-config frame needs an
   ordering contract and races on reconnect, with `X-Profile` (`rest/routes.py:347`) as the
   precedent for a per-run header. **r2 overturns that.** The owner is changing the *protocol*,
   so "inbound frames are attach/stop only" is a description of what to change, not an objection.
   Attach-before-run is already enforced, so ordering is defined; the reconnect race is answered
   by a first-attach-wins rule (spec §5.2) rather than by rejecting the carrier.

   Both carriers are now in scope, which introduces the precedence question the spec raises as
   **D4** — a decision r1 never had to make.

## Planned changes

- `docs/spec/2026-08-05-url4-cache-policy-spec.md` — the spec.
- `docs/plan/2026-08-05-url4-cache-policy.md` — the implementation plan (rule 3: spec then plan).

No code.

**r2 relocation (owner, mid-unit).** r1 located the change in url4-cloud's REST layer. The owner
directed that protocol changes belong in `packages/url4` (+ both HTTP header and protocol frame
as carriers). The spec was rewritten; r1's file was deleted rather than left as a stale sibling.

**The path the owner named does not exist.** `apps/url4-cloud/src/url4_streaming_protocol/` —
with `url4_cloud_nats/` and `url4_cloud_runner/` — is empty, untracked, absent from
`pyproject.toml` (`packages = ["src/url4_cloud"]`) and imported nowhere. The real protocol module
is `packages/url4/src/url4/streaming/protocol/`. Confirmed with the owner before writing.

## Explicitly NOT in this unit

- Implementation (rule 3: starts only on explicit approval in plain words).
- Per-node cache intent — needs url4 grammar, reopens doctrine fork **F4**.
- Any aigateway change: its contract is already complete.

## Acceptance

- Spec follows house structure (modelled on `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md`)
- Every claim about current behaviour carries a `file:line`
- The genuinely open decisions are presented as owner forks, not silently resolved
- Delivered for review before any code

## Outcome

- **Actual files:** `docs/spec/2026-08-05-url4-cache-policy-spec.md` and
  `docs/plan/2026-08-05-url4-cache-policy.md`. No code, per rule 3.
- **Owner decisions taken mid-unit:** protocol lands in `packages/url4` (D9); both carriers
  supported (D10). Four decisions remain OPEN in the spec for review: D1 default, D3 frame shape,
  D4 precedence, D6 header name.

## Deviations

1. **Process deviation** — no Linear issue; MCP unauthenticated (4th occurrence). Branch,
   mirror and `Refs:` all dangling.
2. **Spec rewritten mid-unit** after the owner relocated the change (r1 → r2). Recorded in the
   spec's own revision table rather than hidden.
3. **A named target path did not exist** — see above. Raised rather than silently substituted.
4. **The plan corrects the spec (§0.1).** Spec §4.1 put `as_body_field()` — the mapping to
   aigateway's request-body vocabulary — on the protocol type in `packages/url4`. That violates
   the architecture rule: the protocol must not know an adapter's wire shape. The plan places the
   translation in `apps/url4-cloud` and flags the spec for an r3 amendment rather than diverging
   silently.
5. **r3/r2 — owner locked D1 to cache-ON-by-default**, accepted the ensemble-determinism
   tradeoff (spec §8.2) on the record, and brought the **aigateway chart** into scope. That
   reverses spec D8 ("no aigateway change") and makes the work **cross-app**, so per CLAUDE.md
   rule 8 it is now an epic + 3 sub-issues (`pkg/url4`, `app/url4-cloud`, `app/aigateway`) rather
   than one unit. Checked and recorded: `request_cache_enabled` defaults to `False`
   (`config.py:127-129`) and the chart never sets it, so caching is off in the deployed gateway
   today — Batch 0 exists to fix that.
6. **Two errors of my own, corrected in place.** (i) The plan cited
   `AIGATEWAY_REQUEST_CACHE_ENABLED`; the real alias is **`AIGW_`** — aigateway uses both
   prefixes inconsistently and I guessed. (ii) Flipping D1 exposed a hole in the protocol type:
   with `use_cache: bool = False`, a caller sending `cache: {}` would silently disable caching
   while believing they had expressed no opinion. `use_cache` is now tri-state
   (`bool | None = None`).
7. **The plan was written against the spec's OPEN recommendations**, with §9 stating what
   changes under each alternative. Written this way so the owner reviews spec and plan together
   rather than serialising four decisions first; the plumbing is ~90% invariant across them.
