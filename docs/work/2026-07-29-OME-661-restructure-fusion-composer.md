---
ticket: OME-661
stack: screamingface-studio-frontend
status: in_progress
started: 2026-07-29
finished:
---

# OME-661 — Restructure the fusion composer

## Intent

Rework the Compose panel of
`apps/screamingface-studio/frontend/src/app/(studio)/ensembles/new/page.tsx` so building a fusion
is clear: **members at the top; loop applies to non-judge members only; reduce is its own section;
judge is a separate, optional section (None default); a prominent inline "+ Add model" picker**
sourcing from connected providers (not just the current library). Split the ~2,100-line file into
focused components.

## Planned changes

- Split the compose panel into: `MemberList` / `MemberCard`, `LoopSection`, `ReduceSection`,
  `JudgeSection`, `InlineModelPicker`. Keep `RunConfig` / `RunDetail` behavior intact for now
  (those are OME-662 / OME-663 territory).
- New compose IA (top→bottom): **Members → Loop (members only) → Reduce → Judge (optional)**.
- Inline model picker reads connected-provider models from `model-store`, can add beyond the
  current library.
- Preserve all existing behavior: recipe parse/generate, autosave/save, tabs, runs.

## Test plan

- No test runner is configured for this stack (sdlc mapping waived per canceled OME-657), so
  verification is: run the dev server (localhost:3000) and confirm — add/remove members; loop copy
  excludes the judge; judge is optional with a None default; inline picker adds models beyond the
  library; recipe still generates/parses; save + runs flow intact. Plus `npm run lint` + `tsc
  --noEmit` clean. (Can add Vitest + Testing-Library if desired.)

## Acceptance

- Compose panel matches the new IA; existing behavior preserved; lint + typecheck pass; owner
  visually confirms in the running app.

## Outcome

Iterated with the owner: v1 (single-column Members→Loop→Reduce→Judge) was rejected → landed on a
**stage-based** design.

- **Final design:** two boxed stages — **① Loop** (the members) → **② Reduce** (strategy + optional
  Judge) — in a **two-pane workspace**: stages on the left, a right **inspector rail** (live pipeline
  summary + url4 recipe + Run). Members can **repeat** (self-consistency), the **judge is an
  independent instance** (can reuse a member's model or be a different one), "+ Add model" exists in
  both stages, the picker **closes on add**, and the Judge add-button sits next to the selected chip.
- **Actual files:** `apps/screamingface-studio/frontend/src/app/(studio)/ensembles/new/page.tsx`
  (major rework: `InlineModelPicker`, stage boxes, inspector rail, judge sub-area as a member-style
  card w/ prompt, run keying by slot id); `src/lib/ensemble-store.ts` (`SavedSlot.id`,
  `SavedRunModelResult.slotId?`, `SavedEnsemble.judge` + legacy `judgeId`);
  `src/app/(studio)/ensembles/page.tsx` (list dot key guards duplicates);
  `src/lib/model-store.ts` (model names → `provider/model` handles).
- **Owner refinements folded into this ticket** (owner asked to keep them here, not as separate
  issues): removed the single-member + single-model warnings; judge is a member-style card with a
  system prompt; **model names shown as `provider/model` handles** everywhere (source: model-store),
  redundant `[providerName]` badges dropped. (A speculative sub-issue OME-665 for the handles was
  canceled per "keep them in the same ticket".)
- **Commits:** none yet — awaiting owner sign-off + commit approval (branch
  `OME-661-restructure-fusion-composer`).
- **Gates:** `npx tsc --noEmit` clean · `npm run lint` clean · `/ensembles/new/` + `/ensembles/`
  serve HTTP 200 · rendered layout visually verified via headless screenshot (duplicate member +
  independent judge shown).
- **Deviations / notes:** no test runner configured (sdlc mapping was waived) — verified via app +
  tsc + lint. Terminology stays "ensemble" (rename is OME-658). Rounded shadcn styling kept
  (brand re-skin out of scope). Full per-file component split not done — restructure achieved
  in-file. Duplicate members flow into the mock run path keyed by slot id; deeper run-detail
  handling is OME-663 territory.
