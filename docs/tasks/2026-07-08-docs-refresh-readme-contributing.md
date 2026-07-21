---
id: OME-365
linear_url: https://linear.app/openmined/issue/OME-365/ome-365-docs-refresh-readme-contributing-accuracy-sdlc-url4-landed
status: done
type: task
priority: P1
labels: [repo-dev-processes, agentic, autonomous]
created: 2026-07-08
closed: 2026-07-17
---

README + CONTRIBUTING accuracy fixes. Filed 2026-07-08 from the critical review, right after
the #374 web restore.

**Re-scoped 2026-07-17.** OME-429 (#407) retired the monorepo Pages site, invalidating every
web item (`web/` is now an empty dir, `deploy-website.yml` is gone, the site lives in
`screamingface-web`). Dropped: add `web/` to the layout · `web/public` contribution path ·
"two services" → services + site. Added from drift the ticket predated: `packages/` is no
longer "reserved" (url4 landed), url4 in Releases, gates framed by stack not app.

**Gating fork resolved (owner):** mirrors/ledgers/spec-plan artifacts are **agentic-only
discipline** — they do not bind human contributors. CONTRIBUTING documents the light human
path (issue → branch → conventional commits → PR) and points at `.claude/README.md` for the
agent contract.

Ledger: `docs/work/2026-07-17-OME-365-docs-refresh.md`. Spawned OME-474 (PyPI name `url4` is
taken — `pip install url4` installs a different package, so the docs deliberately say nothing
about installing the SDK).
