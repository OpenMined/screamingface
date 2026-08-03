---
id: OME-715
linear_url: https://linear.app/openmined/issue/OME-715/re-sync-the-screamingface-design-skill-to-sfds-v2-its-snapshot-is-a
status: done
type: task
priority: P2
labels: [repo, autonomous, agentic]
created: 2026-07-31
closed: 2026-08-03
---

# OME-715 — re-sync the screamingface-design skill to SFDS v2

The skill's `reference/` snapshot was dated 2026-06-11; the live system is **SFDS v2.0**, served
today as `?v=20260731a`. The skill's own drift rule says the live site wins.

They diverged structurally: **74 → 628** custom properties, a 12-step primitive scale model with
APCA-solved contrast, EB Garamond → **Parastoo**, Rubik → **IBM Plex Sans**, and `--gain` flipping
from **green to gold**.

## The change that mattered

v2 has **two registers**. `[data-brand="marketing"]` overrides *only* the accent-family aliases;
the **app register is the default**, where `--accent` is **blue** and gold is `--brand`/`--gain`,
"rationed to the win". The old skill said the opposite for product surfaces, so an agent following
it would have built something the live system forbids — which is exactly what `OME-716` was about
to do.

## Done

`tokens.css`, `tokens.json`, `style.css` and `fonts.css` re-pulled **verbatim** and verified by
re-fetch + `cmp`. `SKILL.md` rewritten. `reference/PROVENANCE.md` added with the version string and
a runnable drift check.

`starter.html` deleted — it no longer exists upstream and its stale copy hardcoded EB Garamond and
Rubik.

Full detail: `docs/work/2026-07-31-OME-715-resync-screamingface-design-v2.md`.
