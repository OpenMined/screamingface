---
id: OME-716
linear_url: https://linear.app/openmined/issue/OME-716/re-skin-the-admin-console-on-screamingface-design-system-v2-replacing
status: done
type: task
priority: P2
labels: [autonomous, agentic]
created: 2026-07-31
closed: 2026-08-03
---

# OME-716 — re-skin the admin console on ScreamingFace Design System v2

Owner reversal: `OME-707` vendored the OpenMined Design System on the reasoning that internal
operator tooling wears the parent brand. *"I was wrong giving you openmind design."* The console
moves to **SFDS v2**.

> **Missing landing label** — should be `app › aigateway-ui`, which still does not exist. Same
> owner action outstanding for `OME-708`/`OME-709`.

## Getting the register right was the job

v2 ships two registers. `[data-brand="marketing"]` overrides **only** the accent-family aliases;
the **app register is the default**. So on this surface `--accent` is **blue** and carries every
interaction, `--success` marks a healthy account, `--danger` marks destructive actions — and
`--brand`/`--gain` (gold) appear **nowhere**, because gold is "rationed to the win" and an admin
console has no win.

The naive reading of "make it ScreamingFace" is gold everywhere plus a serif headline. Both are v2
anti-rules.

## Verified by measurement, both themes

0 gold painted · 0 rounded corners · 0 shadows · 0 serif elements · `data-brand` null ·
`main` width == viewport. `--gain-solid` resolves correctly to `#e2a35b` — the token is present and
nothing uses it, which is the distinction that matters.

All four `OME-709` behaviours re-verified: dark default, full-bleed, search button aligned to its
input (3px), dialog centred on both axes.

218 tests (up from 181); 35 are `design-system.test.ts`, which asserts the register and anti-rules
against the CSS source so this cannot quietly drift back.

## Notable

Two hardcoded font stacks (`Consolas, Monaco, …`) were found and removed — a font stack is
invisible to the colour gate, so they had survived the entire OMDS build.

`theme.test.tsx` still says "OMDS tokens" in one test title. The append-only test gate refused the
rename (sdlc rule 5); the assertion is correct and unchanged. Known cosmetic wart.

## Shipped separately — it missed its own PR

This work and `OME-715` were committed to `OME-706-admin-api` **after** PR #451 squash-merged
(11:50Z; these landed 12:53Z and 13:32Z). No PR was ever opened for them, so `main` kept serving the
OpenMined Design System for three days while the branch looked "done".

**Squash-merge is what hid it.** `git log origin/main..HEAD` showed 11 commits — 9 of them already
in `main`, flattened into `14d54f0a` — so the branch read as wholly unmerged and the two genuinely
stranded commits did not stand out. Reachability says nothing in a squash-merge repo; the check that
works is content-level (`design-system.test.ts` 404s on `main`). Same failure mode as #380.

Recovered by cherry-picking the 2 commits onto a fresh branch off `main` rather than rebasing all
11. Verified byte-identical to the browser-verified original:
`git diff 1524d090 HEAD -- apps/aigateway-ui .claude/skills/screamingface-design` is empty.

Full detail: `docs/work/2026-07-31-OME-716-console-on-sfds-v2.md`.
