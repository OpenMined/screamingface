---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 7B compact connection panel

## Intent

Turn `sf.connect()` into a narrow, calm notebook control instead of an always-expanded provider
form. Every provider uses the same single-line structure—name, status, optional account, and one
right-aligned action area—and reveals authentication choices only after the researcher asks to
connect. Preserve the engine-origin safety cue, masked secret handling, explicit OAuth navigation,
polling, accessible labels, and equal light/dark treatment.

## Planned changes

- Refactor `packages/screamingface/src/screamingface/_connection_panel.py` to use one unbordered
  shell, compact equal-height rows, and explicit collapsed/method/API-key/OAuth states.
- Update the prior Phase 6C widget expectations that the owner explicitly replaced with the new
  progressive-disclosure contract.
- Add append-only Phase 7B tests for equal row structure, collapsed initial controls, method
  selection, API-key cancellation, OAuth authorization, and connected-state actions.
- Do not regenerate or overwrite the owner's currently modified notebooks in this unit.

## Test plan

- RED: initial rows expose only one `Connect` action and make no provider/auth mutation.
- RED: selecting `Connect` reveals only the provider's supported auth methods plus `Cancel`.
- RED: API-key selection reveals one masked input with `Save`/`Cancel`, never retains the secret,
  and cancellation makes no engine mutation.
- RED: OAuth selection reveals `Authorize`/`Cancel`, starts exactly one flow, and never attempts an
  automatic browser popup.
- RED: connected rows remain compact and expose only `Disconnect`.
- RED: one shell owns the design tokens; nested header, notices, and rows add no duplicate frame.
- GREEN: focused widget tests, full ScreamingFace tests, coverage, and authoritative gates pass.

## Acceptance

- Rows have a stable desktop height and the visible order provider → status/account → action.
- No API-key field or auth-method inventory is visible until `Connect` is selected.
- OAuth requires a deliberate `Authorize` link click after its URL is returned.
- The panel uses square controls, semantic tokens, hairline row rules, no shadows, no outer frame,
  and equivalent light/dark styling under the ScreamingFace design skill.
- Existing connection security, cancellation, polling, and sanitized error behavior remain intact.

## Approved test-contract replacement

The owner's request explicitly replaces Phase 6C's always-expanded control contract: its tests
required OAuth buttons and API-key inputs to exist on initial render, which is incompatible with
the requested collapsed `Connect` state. Those assertions are updated only where the interaction
changed; their security, accessibility, cancellation, escaping, and polling assertions remain.
Per the repository's Confidence-Gate precedent, the authoritative gate is run once with
`--skip-append-only`; every configured Ruff, format, Pyright, test, and coverage gate still runs.

## Implementation progress

- The widget now has one unframed 760px shell, a compact single-line header, and three fixed 48px
  provider rows separated only by hairlines.
- Initial rows expose only `Connect` or `Disconnect`; method selection, masked API-key entry, and
  OAuth authorization are mutually exclusive inline states.
- OAuth deliberately exposes `Authorize` plus `Cancel` after the flow starts. It does not attempt
  a browser popup after the asynchronous kernel round-trip.
- The ScreamingFace design self-check passes in code: square geometry, semantic token references,
  no gradient, no shadow, no purple, and explicit light/dark selectors. The in-app browser was not
  available, so owner visual confirmation in the live notebook remains before closing this ledger.
- Focused panel tests pass (`10 passed`). The full SDK suite passes (`497 passed`, 95.42% coverage),
  and the authoritative configured gates are green with only the documented, owner-approved
  append-only precheck exception.
- The connected account label now appears in muted parentheses immediately after the provider
  name. The focused suite passes with the added ordering contract (`11 passed`), and all configured
  SDK gates remain green.
- Read-only runtime diagnosis found Gemini still `connected` through OAuth and its model route
  registered, while AI Gateway recorded HTTP 502 for every failed chat request. This rules out SDK
  benchmark loading and the connection preflight; the current sanitized engine failure discards the
  Gateway response detail, so available evidence narrows the cause to Gemini Code Assist setup,
  upstream reachability/availability, or malformed upstream response without selecting one.

## Owner-requested refinement

- Move a connected account label from its own metadata column to muted parentheses immediately
  after the provider display name, without changing the 48px row height or action alignment.
- Add a focused ordering assertion before changing the renderer, then rerun the panel and SDK
  gates. Diagnose the separately reported Gemini HTTP 502 from current runtime evidence only; do
  not change execution, engine, or AI Gateway behavior in this refinement.
- Handle engine-persisted `pending` OAuth state on a freshly loaded panel. Without a local
  `OAuthFlow`, render `PENDING` plus an immediate `Cancel` action; cancellation removes the stale
  engine connection and returns the row to collapsed `Connect`. Preserve `Authorize` plus `Cancel`
  when the initiating panel still owns the live flow URL.
- Analyze benchmark fail-fast and provider credential-readiness UX separately without changing
  execution or Gateway code in this unit.
- Extend the same visual system to live `run`/`grade`/`evaluate` progress and final reports. In
  notebooks the default should expose real completed case and judge-request counts instead of
  leaving a paid synchronous cell apparently hung; scripts remain quiet unless explicitly opted
  in. Keep plain values and discovery lists free of decorative widget behavior.
- The persisted-pending regression is covered by the focused panel suite (`12 passed`). The full
  ScreamingFace Ruff, format, Pyright, test, and 95% coverage gates are green with only the already
  documented `--skip-append-only` exception for the owner-approved Phase 6C contract replacement.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** the SDK now owns shared `_display.py` visual tokens and `_progress.py` live
  stage rendering; `Fusion.run`, `Run.grade`, and `Fusion.evaluate` expose the tri-state progress
  control; execution and grading advance it from real completed case/judge work; connection and
  report rendering consume the same foundation; the quickstart/DRACO builders, notebooks, README,
  architecture plan, public contract, task record, and focused tests document and lock the UX.
- **Commits:** `feat(screamingface): polish live benchmark workflows` (this commit).
- **Gates:** authoritative SDK gate green; 527 SDK tests at 95.26% coverage; 135 engine tests at
  95.55% coverage; all seven notebooks regenerate byte-identically; fixtures and wheel/sdist build
  pass. The running Compose stack is healthy and its live registry advertises `web_search` only
  for Claude.
- **Deviations:** progress uses IPython's existing display-update protocol rather than adding a
  second ipywidgets state model. This keeps it optional and dependency-light while sharing the
  exact visual tokens. Successful notebook progress is cleared before the returned value renders;
  safe failure status remains visible when an exception propagates. Owner-requested refinement
  expanded this slice from the connection panel to the shared progress/report foundation and the
  concise direct quickstart/DRACO notebook layouts.
