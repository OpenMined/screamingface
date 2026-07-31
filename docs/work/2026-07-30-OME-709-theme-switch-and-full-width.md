---
ticket: OME-709
stack: aigateway-ui
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-709 — theme switch defaulting to dark, full-width layout, aligned search control

## Intent

Three defects an operator found by looking at the `OME-708` console.

1. **No theme control at all.** The vendored OMDS tokens key dark mode only off
   `[data-theme="dark"]` on `<html>`, and nothing in the app sets it — so the console is stuck in
   light and does not even follow the OS preference. Wanted: a real switch, **defaulting to dark**.
2. **Ragged widths.** One page stacked five different `max-width` values (1100 / 720 / ~606 / ~530
   / 420), so every block began at the same left edge and ended somewhere different.
3. **The search button sits below its input.** The button is a sibling of the whole `.ui-field`
   (label + control + hint), so it aligns to the bottom of that three-row stack instead of to the
   input itself.

## Owner decision on the widths

Proposed harmonising the five values into a named scale. **Owner instruction: remove `max-width`
entirely — "it's ugly".** The layout goes full-bleed with padding rather than trading five arbitrary
caps for three.

Recorded because it has a cost worth naming once: on a very wide display prose lines get long, and
long measures are harder to read. That is the owner's call, and it is made. Padding keeps text off
the window edge; nothing caps it.

## Planned changes

- `src/app/globals.css` — drop every `max-width`; keep horizontal padding. Fix the search row so
  the button aligns to the input, not to the field stack.
- `src/app/accounts/[id]/detail.module.css`, `credentials/new/form.module.css` — same width removal.
- `src/app/theme.tsx` (new) — client theme switch writing `data-theme` to `<html>` and persisting.
- `src/app/layout.tsx` — a blocking inline script in the document head applying the stored theme
  before first paint, defaulting to dark.
- `src/app/theme.test.tsx` — the switch's behaviour and the no-flash contract.

## The flash is the hard part

A React effect runs *after* first paint, so a theme applied there renders light and then flips —
visibly, on every navigation. The stored choice must reach `<html>` from a synchronous inline
script in the head. That script is a fixed string literal taking no runtime input, which is what
makes injecting it safe here.

## Test plan (RED first)

- default is dark when nothing is stored
- a stored choice wins over the default
- toggling writes both the attribute and storage
- the inline script interpolates no runtime value
- an unavailable `localStorage` still yields a usable theme rather than throwing
- the search button and its input share a baseline row

## Acceptance

- `run_gates.py aigateway-ui` green
- Verified in a browser: loads dark with no flash, switch flips it, choice survives reload
- No `max-width` left in app CSS; search button aligned

## Outcome

- **Gates:** `run_gates.py aigateway-ui` — all five green. **181 tests** (15 new for the theme).

- **Verified in a browser, measured rather than eyeballed:**
  - default theme `dark`, body `rgb(46,43,59)` = `#2e2b3b`
  - **no flash**: reading `data-theme` with ZERO wait on load already returns the stored choice,
    before React hydrates. The script is in `<head>`, neither `async` nor `defer`.
  - toggle flips the document, persists to storage, and the choice survives a reload
  - search button and input tops differ by **1px** (was 91px)
  - no `max-width` anywhere in app CSS; `main` width == viewport width
  - dialog opens centred, closes on the × and on Escape

## Deviations from the plan

1. **The pre-paint script is a SERVED FILE, not inline.** Planned as an inline `<script>`. A guard
   flagged `dangerouslySetInnerHTML`, and on reflection the served form is simply better: the
   document contains no injected HTML at all, so a future CSP needs no `'unsafe-inline'`. Cost is
   one cached same-origin request. `public/theme-init.js` mirrors `applyStoredTheme`, and
   `theme.test.tsx` asserts they agree on the storage key, the default and the attribute so they
   cannot drift silently.
2. **`useSyncExternalStore`, not `useState` + effect.** The effect version is a lint ERROR here
   (`react-hooks/set-state-in-effect`, error-level via eslint-plugin-react-hooks v6) and is also
   wrong on its merits: the theme lives on `<html>`, written before React exists, so it is external
   mutable state and syncing it after paint reintroduces a flash in the switch's own label.
3. **`@next/next/no-sync-scripts` is disabled on one line, with the reason inline.** The rule is a
   performance heuristic against render-blocking scripts; blocking is the entire requirement here.
4. **The search fix was NOT the alignment rule I first wrote.** Removing `max-width` made the field
   `flex: 1 1 320px` grow to fill the row, pushing the button onto a second line — a 91px gap that
   *looked* like the original misalignment but had a different cause. Fixed with `flex-wrap: nowrap`
   and a shrinkable `flex: 0 1 20rem` basis, so the control is sized without reintroducing a cap.
5. **`vitest.setup.ts` now installs a real in-memory `localStorage`.** Node 22+ ships its own
   experimental `localStorage` global; on Node 25 it shadows jsdom's while being disabled, so
   `window.localStorage` exists but has no methods. Every storage test failed with "clear is not a
   function", which reads like a bug in the code under test rather than an environment artefact.
6. **`<dialog>` needed `margin: auto` restored.** OMDS's reset sets `* { margin: 0 }`, which strips
   the centering a native dialog does for itself and pinned the modal to the top-left corner.

## Note on the width decision

Full-bleed is now the layout. The cost named at the start stands: on a very wide display prose
lines get long. Nothing caps them by design.
