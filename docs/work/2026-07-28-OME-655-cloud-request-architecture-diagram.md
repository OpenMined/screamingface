---
ticket: OME-655
stack: repo
status: in_progress
started: 2026-07-28
finished:
---

# OME-655 — Add subsidized cloud-hosted request-architecture diagram

## Intent

The `docs/diagrams/screamingface-request-architecture` diagram depicts only the
local / BYOK topology (engine + gateway on your machine, "your keys stay in the
gateway"). The product also offers a **subsidized cloud** path where OpenMined runs the
engine → providers chain and funds the compute + provider tokens
(`docs/positioning.md`, `docs/screamingface-v1-launch-plan.md`). This unit adds a cloud
variant so the local-vs-subsidized choice is visible, and scopes the local-path "keys"
legend correctly (positioning warns "no middleman" belongs to the local path only).

## Planned changes

- `git mv` the existing pair → `…-local-{light,dark}.{svg,png}`; eyebrow marks local mode.
- New `…-cloud-{light,dark}.svg`: dashed structural boundary wrapping Engine + Gateway +
  Providers + sub-boxes, labelled "OPENMINED CLOUD · SUBSIDIZED COMPUTE + TOKENS"; an
  "ON YOUR MACHINE" tag over the client; gateway sub-line → "subsidized tokens"; legend →
  subsidized-compute wording (no "keys stay in the gateway").
- Render four PNGs via `rsvg-convert -z 2`.

## Test plan

Visual verification (no automated tests for static SVG assets):
- Cloud PNGs: boundary encloses Engine+Gateway+Providers+sub-boxes; label above; client
  tagged "ON YOUR MACHINE" and outside the band; request arrow crosses the boundary;
  subsidized legend; no keys claim.
- Local PNGs: topology unchanged; eyebrow marks local; keys legend retained.
- Both themes: true white / true dark bg; `screamingface-design` self-check (no purple, no
  radius, no shadow, mono type, greyscale + single amber spark).

## Acceptance

- Four rendered PNGs + two renamed + two new SVGs under `docs/diagrams/`, brand-compliant
  in both themes; `git status` shows two renames + one new cloud pair (svg+png ×2).

## Outcome

- **Actual files:** as planned. Renamed (untracked, so plain `mv` not `git mv`):
  `screamingface-request-architecture-{light,dark}.{svg,png}` →
  `…-local-{light,dark}.{svg,png}` (eyebrow → "LOCAL · RUNS ON YOUR MACHINE · YOUR KEYS,
  YOUR SUBSCRIPTIONS"; keys legend retained). New:
  `…-cloud-{light,dark}.{svg,png}` (dashed boundary x=326 y=120 w=892 h=305 wrapping
  Engine+Gateway+Providers+sub-boxes; label "OPENMINED CLOUD · SUBSIDIZED COMPUTE +
  TOKENS"; "ON YOUR MACHINE" client tag; gateway line "subsidized tokens"; legend
  "subsidized compute, funded by OpenMined · no keys of your own needed").
- **Commits:** pending — not committed (owner mid-work on `OME-641-brand-refresh` with
  other uncommitted changes; awaiting owner decision on branch/commit).
- **Gates:** n/a — static SVG assets. Rendered all four via `rsvg-convert -z 2` (no XML
  errors); visual check of all four PNGs passed the `screamingface-design` self-check in
  both light and dark (no purple, radius 0, no shadow, mono type, greyscale + single
  amber spark).
- **Deviations:** original files were untracked → used `mv` instead of `git mv`; local
  variant given only an eyebrow tweak (no new boundary) to keep scope tight.
