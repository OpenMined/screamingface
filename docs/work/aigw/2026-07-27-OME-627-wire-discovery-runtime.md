---
ticket: OME-627
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-627 — Wire the bounded discovery runtime into the detailed model-parameters contract

## Intent

The bounded discovery transport, the TTL+stale observation cache and the `discover_chat_parameter_snapshot`
port all exist and are hardened, but nothing in the application ever constructs them. As a result
`/v1/model-parameters` serves a hardcoded `freshness` constant — `{"stale": false, "degraded": false}` —
which asserts that nothing is stale and nothing is degraded on a contract that has never observed
anything at all, and omits the locked v1 `observed_at` / `expires_at` window entirely (§6.2).

This unit lands the runtime and the consumption seam: a `DiscoveryRuntime` that owns the bounded
client, the cache and the wall clock; a port that lets a provider declare its discovery source
identity *before* a fetch (the cache needs source + canonical model + revision up front); and the
detail route composing real freshness from the cache outcome. No provider declares a source yet, so
every contract is still served from static observations — with an honest "never observed" window.

Making provider catalog evidence model-specific, and letting it restrict effective support, is the
next unit; keeping the two apart avoids presenting the wiring as if it also made OpenRouter support
model-specific.

## Planned changes

- `apps/aigateway/src/aigateway/core/discovery_runtime.py` (new) — `DiscoverySourceRef`,
  `DiscoveryOutcome`, `static_discovery_outcome()`, `DiscoveryRuntime.observe()`.
- `apps/aigateway/src/aigateway/core/plugin_base.py` — new `chat_discovery_source()` hook,
  defaulting to `None` (no dynamic source).
- `apps/aigateway/src/aigateway/config.py` — discovery enable flag, cache TTL / stale window /
  max entries, request timeout, byte cap.
- `apps/aigateway/src/aigateway/main.py` — construct the runtime in `create_app`, expose it as
  `app.state.discovery_runtime` (`None` when disabled).
- `apps/aigateway/src/aigateway/routes/model_parameters.py` — replace `_LOCAL_FRESHNESS` with the
  runtime's composed window.
- `apps/aigateway/tests/unit/core/test_discovery_runtime.py` (new).
- `apps/aigateway/tests/unit/test_model_parameters_discovery_wiring.py` (new).

## Test plan

RED first, in `tests/unit/core/test_discovery_runtime.py`:

- No declared source → the client is never touched, the cache is never touched, the outcome is
  static with `observed_at`/`expires_at` null and both flags false.
- The cache key carries the source, the canonical model id and the source revision.
- A successful fetch → `fresh`: `observed_at` is the wall-clock instant of the fetch, `expires_at`
  is that instant plus the configured TTL, both flags false.
- A second call inside the TTL reuses the cached snapshot (one upstream attempt) and keeps the
  ORIGINAL `observed_at` — the window describes the evidence, not the request.
- Expiry then a source failure → `stale`: last-good snapshot, `stale` true, `degraded` false,
  `observed_at` still the original fetch instant.
- Failure past the stale window → `degraded`: no snapshot, `degraded` true, and no fabricated
  observation timestamp.
- A declared source whose fetch reports NOT ATTEMPTED degrades instead of caching "no evidence"
  as fresh.
- The runtime passes the model and its own bounded limits to the provider and nothing else — no
  credential, no caller-built URL.
- A non-`DiscoveryError` fault from a provider propagates rather than being swallowed as degraded.

In `tests/unit/test_model_parameters_discovery_wiring.py`:

- The app exposes a `DiscoveryRuntime` carrying the configured bounds; disabling it yields `None`.
- The detail contract emits the locked v1 freshness window with all four keys.
- The chat route modules reference nothing from the discovery runtime — dispatch cannot discover.

## Acceptance

- Chat dispatch performs no discovery.
- Cache identity = source + canonical model + source revision.
- Static observations still serve every contract; a provider with no source is unaffected.
- No credentials and no caller-controlled URL reach discovery; the model reaches the runtime only
  after canonical-id validation.
- Fresh / stale / degraded map to distinct freshness windows and a degraded outcome fabricates no
  observation timestamp.
- Full aigateway gate green; no prior test modified.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `core/discovery_runtime.py` (new) — `EvidenceCache` / `DiscoverablePlugin` ports,
    `DiscoveryOutcome`, `_Observed`, `static_discovery_outcome()`, `DiscoveryRuntime`.
  - `core/parameter_discovery.py` — `DiscoverySourceRef`.
  - `core/parameter_discovery_cache.py` — `SystemMonotonicClock`, `ObservationCache.limits`.
  - `core/plugin_base.py` — `chat_discovery_source()` hook, default `None`.
  - `config.py` — six discovery settings.
  - `main.py` — `_build_discovery_runtime()`, `app.state.discovery_runtime`.
  - `routes/model_parameters.py` — `_discovery_outcome()`; `_LOCAL_FRESHNESS` removed.
  - `tests/unit/core/test_discovery_runtime.py` (new, 11 tests).
  - `tests/unit/test_model_parameters_discovery_wiring.py` (new, 6 tests).

  Two files beyond the plan: `parameter_discovery.py` (the source ref belongs with the
  discovery port, not the runtime that consumes it) and `parameter_discovery_cache.py` (see
  Deviations).

- **Commits:** `ff5aeab4` — feat(aigateway): wire the bounded discovery runtime into the detailed
  contract. Source + tests only (9 files).
- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN (ruff check, ruff
  format, pyright, no-enterprise, pytest with `--cov-fail-under=80`). Three attempts: the first
  two were a formatting diff and four pyright `TestClient.app` attribute errors, neither a logic
  change. Full suite before the gate: 1728 passed, 7 skipped, no prior test modified
  (`git diff HEAD -- apps/aigateway/tests` shows zero removed lines).

- **Deviations:**
  1. **`ObservationCache.limits` and `SystemMonotonicClock` added to the cache module.** The
     published `expires_at` must be derived from the TTL the cache actually expires on. Passing
     the TTL to the runtime separately would be a second source of truth whose drift is
     invisible — the contract would advertise a window the cache does not honour. Both additions
     are read-only/new and change no existing behaviour.
  2. **The freshness object grew from `{stale, degraded}` to the locked v1 four-key shape.** This
     completes §6.2's response shape (`observed_at` / `expires_at` were documented from the start
     and marked "arrives later" in the route); it adds keys and removes none. No existing test
     asserted the two-key shape at the route level.
  3. **A degraded outcome publishes null timestamps rather than "now".** A window implies evidence
     stands behind the contract; a degraded read has none.
  4. **A declared source whose fetch reports NOT ATTEMPTED is treated as a failed attempt.** The
     cache reads every normal return as a successful refresh, so returning "no evidence" there
     would store it labelled fresh and evict the last good snapshot.
  5. **Discovery defaults to enabled.** Dynamic evidence can only RESTRICT what a contract claims,
     so running without it is the more permissive state, not the safer one. No provider declares a
     source yet, so this commit adds no outbound traffic on its own.
