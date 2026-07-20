---
ticket: OME-365
stack: repo
status: done
started: 2026-07-17
finished: 2026-07-17
---

# OME-365 — Docs refresh: README + CONTRIBUTING accuracy

## Intent

`README.md` and `CONTRIBUTING.md` are the front door for both humans and agents, and neither
has been touched since 2026-07-08 (`README` at the re-foundation commit #371, `CONTRIBUTING`
at the OME-358 SDLC-adoption commit #376). The repo moved underneath them: `packages/url4`
landed with a release lane, `run_gates.py` became the canonical gate command, `docs/` grew a
real SDLC tree, and OME-429 retired the monorepo Pages site. A contributor following either
file today is told things that are false.

## Scope re-cut (2026-07-17)

The ticket was filed 2026-07-08 immediately after the #374 web restore, to make the docs
reflect it. `3f6bfe3` (OME-429, #407) then **retired** the Pages site — `web/` is an empty dir,
`deploy-website.yml` is gone, CLAUDE.md now states the site lives in `screamingface-web`.
Three of the original nine items were therefore invalid and are **dropped**; executing them
would have documented a lane that does not exist:

- ~~README: add `web/` to the layout~~
- ~~CONTRIBUTING: `web/public` contribution path (edit → PR → auto-deploy on merge)~~
- ~~README: "two services" → services + site~~ (it *is* two services again)

Added in their place, from drift the original ticket predates:

- README `packages/` line still says "reserved — url4-python-sdk lands here first"; url4 has
  landed (v0.1.0, LICENSE, README, `py.typed`, release lane `release-url4.yml`). It is **not**
  on PyPI under that name — see Deviations / OME-474.
- CONTRIBUTING Releases covers aigateway + scoreboard only; url4 (`url4-v*`) is missing.
- CONTRIBUTING frames gates as `cd apps/<app>`, silently omitting `packages/url4` — the
  stacks are `aigateway`, `scoreboard`, `url4` per `.claude/sdlc.local.md`.

**Gating fork resolved (owner, 2026-07-17): agentic-only discipline.** `docs/tasks/` mirrors,
`docs/work/` ledgers, and spec/plan artifacts bind agents, not humans. CONTRIBUTING documents
the light human path (issue → branch → conventional commits → PR) and points at
`.claude/README.md` for the agent contract.

## Planned changes

- `README.md` — screamingface.ai link on the pitch; stale `docs/` line → real tree;
  `packages/` → url4 landed; test snippet → `run_gates.py <stack>`.
- `CONTRIBUTING.md` — `run_gates.py <stack>` canonical; stack-not-app framing; url4 in
  Releases; human path inline; Reference → `.claude/README.md`.
- `docs/tasks/2026-07-08-docs-refresh-readme-contributing.md` — reconcile drift vs Linear
  (`status`, `labels`, `linear_url`), then close.

## Test plan

No automated gates exist for this change — stated plainly rather than faked:

- `run_gates.py <stack>` resolves a stack from `.claude/sdlc.local.md` (`aigateway`,
  `scoreboard`, `url4`). Docs are not a stack → it fail-configs by design.
- `repo-checks.yml` triggers only on `.claude/skills/sdlc-**`, `.claude/scripts/**`, and its
  own file. A `README.md`/`CONTRIBUTING.md` PR runs **zero CI**.

Manual verification instead:

- Every command in both files executes as written (each `run_gates.py <stack>` invocation,
  `uv sync`, the run lines, `git config core.hooksPath`).
- Every referenced path exists; every link resolves.
- No stale referent survives: no `web/public`, no `deploy-website.yml`, no `packages/` as
  "reserved".
- A human reading CONTRIBUTING top-to-bottom is never told to write a ledger or a mirror.

## Acceptance

- Both files describe the repo as it is at `ad8e809`.
- The three gate commands run green from a clean checkout.
- Mirror agrees with Linear and is closed.

## Outcome

- **Actual files:** as planned (`README.md`, `CONTRIBUTING.md`, the OME-365 mirror), plus two
  unplanned: this ledger and `docs/tasks/2026-07-17-url4-pypi-name-taken.md` (the OME-474
  mirror — see Deviations).
- **Commits:** see the PR; single `docs(OME-365):` commit.
- **Gates:** none apply to the change itself — docs are not a stack, and no CI matches
  `README.md`/`CONTRIBUTING.md`. What *was* verified, because the docs make claims about it:
  all three documented gate commands were executed and are green —
  `run_gates.py url4` ✓, `run_gates.py scoreboard` ✓, `run_gates.py aigateway` ✓ (ALL GATES
  GREEN each). The documented error path was executed verbatim: `run_gates.py docs` →
  `CONFIG ERROR: stack 'docs' not in .claude/sdlc.local.md (has: aigateway, scoreboard, url4)`.
  Every referenced path exists; `screamingface.ai` → 200; the legacy tag resolves.

- **Deviations:**
  1. **Scope re-cut** (owner-approved, above): 3 web items dropped as invalid post-OME-429;
     url4/packages items added. The ticket was retitled off "after web restore".
  2. **Spawned OME-474.** Verifying my own draft `pip install url4` line revealed the PyPI
     name `url4` belongs to Andrew Trask's separate `iamtrask/url4` (v0.1, 2026-02-22). This
     repo's `packages/url4` v0.1.0 is unpublished, and `release-url4.yml` instructs an owner
     to "reserve the `url4` project" — which is impossible. The draft line was removed; both
     files now say nothing about installing the SDK rather than something false. OME-474
     carries the owner fork. Its mirror rides in this PR (a mirror is due at create; a
     dedicated PR for one 15-line file was not worth it).
  3. **Two of my own drafted claims were wrong and were caught by verification, not review:**
     "the same gates CI runs, in the same order" (the runner adds an append-only check CI does
     not run) and a documented `Workstream (Epic)` label row (that group no longer exists in
     Linear — the OME-474 filing was rejected on it). Both corrected.
  4. **Label taxonomy drift, left alone (out of scope).** OME-365 carries
     `repo-dev-processes`, which current `main`'s task-board card no longer registers — its
     landing set is `app/aigateway`, `app/scoreboard`, `pkg/url4-python-sdk`, `repo`. The
     mirror now matches Linear. Card/Linear reconcile is an owner action, also needed for the
     missing `Epic` group.
