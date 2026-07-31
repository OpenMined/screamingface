---
id: OME-716
linear_url: https://linear.app/openmined/issue/OME-716/re-skin-the-admin-console-on-screamingface-design-system-v2-replacing
status: in_review
type: task
priority: P2
labels: [autonomous, agentic]
created: 2026-07-31
closed:
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

Full detail: `docs/work/2026-07-31-OME-716-console-on-sfds-v2.md`.
