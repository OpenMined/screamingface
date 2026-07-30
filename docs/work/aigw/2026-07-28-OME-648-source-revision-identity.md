---
ticket: OME-648
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-648 — Carry, publish, validate and hash the dynamic source revision in the detailed contract

## Intent

Every dynamic provider stamps its snapshot with a `source_revision` that versions the gateway's
**reading** of a source, not merely the URL. The spec puts "source, revision, and freshness
metadata" in Included scope, and the plan states that `contract_id` / `context.revision` change when
the provider evidence revision changes.

Part of this landed with OME-647, which had to thread the revision into the identity digest to make
the renamed combined-source revision reach contract identity. What remains:

1. **Publish** the revision as non-secret contract metadata.
2. **Validate** that a provider's returned snapshot revision agrees with the source reference used
   as the cache key.
3. **Mutation tests** proving a revision change moves *both* opaque IDs even when the resulting
   observations are byte-identical.

Carrying it through route composition and folding it into both digest inputs is already done —
`build_model_parameter_document` takes `source_revision` and both `_opaque_id` calls hash the same
`digest_inputs` tuple. This ledger re-verifies that rather than re-implementing it.

## Verified before starting

- All three discovering plugins already pair the same constant on both sides
  (`chat_discovery_source` ↔ the returned snapshot): OpenRouter `SNAPSHOT_SOURCE_REVISION`,
  HuggingFace `ROUTER_SOURCE_REVISION`, Gemini `DISCOVERY_SOURCE_REVISION`. The agreement check is
  therefore a no-op for every shipping provider and fires only on a genuine defect.
- Every existing runtime test double also stamps the matching revision
  (`test_discovery_runtime.py`, `test_auth_scoped_discovery.py`), so no prior test needs to change.

## Design decisions

**Publish inside `context`, not `freshness`.** My first instinct was `freshness`, because the
revision is null in exactly the cases the timestamps are null (no dynamic source; a degraded read).
That is a correlation of lifecycle, not of meaning, and it loses to a stronger property: in this
document `freshness` is *defined* as the one block excluded from the identity digest, because it is
time-varying. `source_revision` is the opposite — it is hashed, and hashing it is the entire point
of this work item. Every field already in `context` (`scope`, `auth_mode`, `revision`) is a digest
input, so `context` is precisely the identity-bearing metadata block, and the review's phrase "at
the appropriate scope" points at the contract-scope block. Putting a hashed value inside the
documented not-hashed block would mislead the next reader about which fields move an id.

The two revisions sitting side by side stay distinguishable by construction: opaque digests carry
the `pc_` / `ctx_` prefixes that exist for exactly that domain separation, while this one is a
readable provenance label.

Secondary, and deliberately not the reason: `context` is asserted field-wise by existing tests
while `freshness` is pinned by seven exact-equality assertions, so this placement also needs no
prior test to change.

**One value, published and hashed by construction.** The composer serves and hashes the same
`source_revision` argument, so the published field and the digest input cannot drift. This is the
same reasoning `_section_revision` already embodies in this module: bind the two structurally rather
than by memory.

**The agreement check belongs in the runtime, beside the `no_snapshot` check.** That is where the
cache key is built from `ref.revision`. A snapshot stamped with a different revision would be stored
under a key asserting a reading that did not produce it, and then served for the declared reading.
Failing the attempt routes it to the honest stale/degraded path, exactly as a fetch failure does.

## Planned changes

- `src/aigateway/core/model_parameter_contract.py` — publish `context.source_revision` from the
  argument already hashed.
- `src/aigateway/core/discovery_runtime.py` — reject a snapshot whose `source_revision` disagrees
  with the `DiscoverySourceRef` used as the cache key.
- Tests — a new module for revision identity: the mutation matrix over both opaque IDs, the
  published field across all three window states, and the agreement check.

## Test plan

RED first:

1. Two snapshots differing only in `source_revision`, with byte-identical observations, move **both**
   `contract_id` and `context.revision`. (The review's probe showed both staying equal.)
2. The revision is published in the served document.
3. A contract with no dynamic source publishes `source_revision: null` — key present, as with the
   timestamps.
4. A degraded read publishes `source_revision: null` and no timestamps.
5. A stale read still publishes the revision — degradation is not amnesia.
6. A provider whose snapshot revision disagrees with its declared ref is refused, and the runtime
   degrades instead of caching the mismatch.
7. Agreement holds for every shipping discovering plugin (a regression guard on the pairing).
8. Evidence-only preserved: no `gateway.status`, `/v1/models`, or dispatch movement.

## Acceptance

- A source/parser revision change moves both opaque IDs with byte-identical observations.
- The published revision is present and carries no secret material.
- A snapshot disagreeing with its cache-key reference is rejected rather than served.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files:**
  - `src/aigateway/core/model_parameter_contract.py` — publishes `context.source_revision` from the
    argument already folded into the digest.
  - `src/aigateway/core/discovery_runtime.py` — a snapshot whose `source_revision` disagrees with
    the `DiscoverySourceRef` used as the cache key raises `DiscoveryError("revision_mismatch")`,
    disposed of exactly like any other failed attempt.
  - `tests/unit/core/test_contract_source_revision_identity.py` — NEW, 15 tests: the mutation
    matrix over both opaque IDs, publication across all window states, the agreement check
    (including that a mismatch never evicts a good entry), two production-wiring tests through
    `/v1/model-parameters`, and a pairing regression guard.
- **Commits:** `2eca9cb4` — `feat(aigateway): publish and enforce the dynamic source revision`
  (`Refs: OME-648`).
- **Gates:** `run_gates.py aigateway` → ALL GATES GREEN, **including the append-only test check**
  run without any skip — this unit changed no prior test, so the "ask before changing a prior test"
  boundary was never reached. Full suite **2040 passed / 40 skipped** (from 2025 — net +15).
  Enabled-OpenRouter conformance → 11 passed.
- **Deviations:**
  - **Three of the five required bullets were already satisfied by OME-647**, which had to thread
    the revision into the digest to make the renamed combined-source revision reach contract
    identity. Carrying it through route composition and folding it into both opaque IDs were
    therefore *verified* here rather than re-implemented; the mutation matrix now proves both, which
    is what the review actually asked for.
  - **Placement changed during design.** The first plan was `freshness.source_revision`, on the
    argument that the revision is null in exactly the cases the timestamps are null. That lost to a
    stronger property: `freshness` is *defined* in this document as the block excluded from the
    identity digest, and this value is hashed. Publishing a hashed value inside the documented
    not-hashed block would mislead the next reader about which fields move an id. `context` — where
    every existing field is a digest input — is the correct home.
  - **The defect reproduced concretely before the fix.** The RED run showed a snapshot stamped
    `probe:reading-2` being stored *and served* under the cache key for `probe:reading-1`, which is
    the failure the agreement check now prevents.
  - **No shipping provider changes behavior.** All three discovering plugins already pair the same
    constant on both sides, and every existing runtime test double stamps the matching revision, so
    the check is a no-op today and fires only on genuine drift. Verified before implementing rather
    than assumed.
  - **A weak test was removed before commit, not shipped.** An early cross-provider guard asserted
    mere truthiness of the Gemini and HuggingFace constants, which proves nothing; it was narrowed
    to the provider whose revision actually moved, with a note that the other two assert the same
    pairing at their own snapshot sites.
  - **Two planned test-plan items are covered indirectly, not by a dedicated route test.** Test-plan
    items 4 and 5 (a degraded read publishes null; a stale read still publishes the revision) hold
    because the route derives the argument as `snapshot.source_revision if snapshot else None`, and
    the runtime tests prove a stale hit keeps the good snapshot with its revision intact. Both
    branches of that expression are exercised at route level — non-null via OpenRouter, null via
    Anthropic — but no route test forces a *degraded* OpenRouter read specifically.
  - **No schema/model change**, so stack rule S1 does not apply.
