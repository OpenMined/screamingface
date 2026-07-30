---
ticket: OME-684
stack: repo
status: in_progress
started: 2026-07-30
finished:
---

# OME-684 — Diagrams for the gateway-identity workflow

## Intent

Fourth unit of the gateway-identity initiative. The three code/chart units are done; this makes the
resulting workflow legible to a developer who did not build it — above all the part that is
counter-intuitive: identity is NOT forwarded as headers end to end, because the App and the Runner
are different Pods, so it is captured, serialized into the Job spec, and re-rendered.

## Planned changes

- `docs/diagrams/gateway-identity-flow.mmd` — sequence: what each hop carries.
- `docs/diagrams/gateway-identity-topology.mmd` — deployment: who may reach aigateway and why.
- `docs/diagrams/gateway-identity-auth-modes.mmd` — the three auth modes and the refused combinations.
- `docs/diagrams/gateway-identity-*.svg` / `.png` — the committed renders (repo convention).
- `docs/diagrams/gateway-identity.md` — index page embedding the mermaid inline.

WHY `.mmd` rather than the hand-written SVG style of `url4-cloud-execution-flows.gen.py`: mermaid
stays diffable and renders inline on GitHub, so the source a developer edits is the source that is
reviewed. Rendering is a plain `mmdc` invocation, documented in the index page — a committed
generator script was tried and removed at the owner's request.

## Test plan

- Every `.mmd` renders without a mermaid parse error.
- Each diagram produces both an `.svg` and a `.png`.
- Content check against the code, not the intent: header names, env var names, function names and
  status codes in the diagrams must match `job_env.py`, `connector.py`, `gateway_identity.py`.

## Acceptance

- A developer can read the three diagrams and correctly answer: where does identity come from, why
  is it not plain header forwarding, and why may aigateway trust it.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — 3 `.mmd`, 3 `.svg`, 3 `.png`, the generator, and the index page.
- **Commits:** not committed yet.
- **Gates:** all three render; each PNG inspected visually (not just exit codes — see Deviations);
  the index's mermaid blocks verified in sync with the `.mmd` sources.
- **Deviations:**
  - **The generator does NOT use `rsvg-convert`** like the older hand-written generators. Mermaid
    puts labels in `<foreignObject>`, which rsvg cannot render — the first PNGs came out with EVERY
    label missing. Forcing `htmlLabels: false` to work around it made rsvg collapse the whitespace
    in mermaid's `tspan` output ("onePodperrun"), so both outputs now come from mermaid-cli
    (Chromium). CONSEQUENCE: the committed SVGs contain foreignObject — fine in a browser, on
    GitHub, or in a docs site, but a plain SVG rasterizer will drop the text. Use the PNG there.
  - Two mermaid syntax traps hit on the way, worth knowing before editing the `.mmd`: a `;` inside
    label text is a STATEMENT SEPARATOR and splits the line, and `<...>` in message text is parsed
    as an HTML tag (`GET /?q=<url4>` broke the parse).
  - `Note over X` sizes to that participant's box, not to the text, so long notes were clipped.
    They now span two participants (`Note over A,J`).
  - The generator also **syncs the index page's mermaid blocks from the `.mmd` files**, so the
    inline copy that renders on GitHub cannot drift from the rendered images.

## What a reader gets

1. `gateway-identity-flow` — the seven hops and what each carries, with the non-obvious part called
   out: it is not header forwarding, because the App and the Runner are different Pods.
2. `gateway-identity-topology` — who may reach aigateway, why there is no Ingress, and the
   NetworkPolicy AND/OR selector trap.
3. `gateway-identity-auth-modes` — the three modes, the 401 paths, and the three chart
   configurations that refuse to render.
