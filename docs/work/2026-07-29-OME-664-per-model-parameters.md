---
ticket: OME-664
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-664 — Per-model parameters in the composer

## Intent

Give each member model an **"Add parameter"** dropdown of available inference params; the user
picks one, sets its value, can add several, and remove them. Persist on the slot. Builds on the
OME-661 composer member cards.

## Planned changes

- `lib/ensemble-store.ts`: extend `SavedSlot` with `params?: { key: string; value: string }[]`.
- `(studio)/ensembles/new/page.tsx`: a `ParamEditor` under each member card's system prompt — an
  "Add parameter" dropdown (only not-yet-added params), per-param typed input, remove per param.
- Param catalog: temperature, top_p, top_k, max_output_tokens, frequency_penalty,
  presence_penalty, reasoning_effort (low/med/high), seed, stop.

## Test plan

- No test runner (waived) → verify in-app (add/remove params, values persist via autosave, only
  unused params offered) + `npx tsc --noEmit` + `npm run lint` clean.

## Acceptance

- Each member card can attach multiple params with values; persisted; lint + tsc pass; owner
  confirms in-app.

## Outcome

- **Actual files:** `src/lib/ensemble-store.ts` (`ModelParam` type + `SavedSlot.params?`);
  `src/app/(studio)/ensembles/new/page.tsx` (`PARAM_CATALOG`, `ParamEditor` component,
  `updateSlotParams`, rendered under each member card's system prompt).
- **Commits:** on branch `OME-661-restructure-fusion-composer` (combined UI-revision branch) —
  `feat(desktop): add per-model parameters to composer members`, `Refs: OME-664`.
- **Gates:** `npx tsc --noEmit` clean · `npm run lint` clean · `/ensembles/new/` HTTP 200 · render
  verified (an "+ Add parameter" control on each member card; judge card unchanged).
- **Deviations:** params are NOT serialized into the url4 recipe (consistent with prompts/weights
  being omitted); param editor applies to members only (judge left prompt-only per ticket scope).
