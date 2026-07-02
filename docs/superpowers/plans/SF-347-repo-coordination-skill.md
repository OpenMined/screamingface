# Plan: Multi-developer coordination — repo skill + enforcement + doc consolidation

## Context

ScreamingFace now has 10+ developers landing changes concurrently. The stated ask was to "define a way to
separate our output" and encode it in a **Claude skill attached to the repo**, covering (1) the monorepo /
app-package model, (2) how GitHub Actions are separated & identified, and (3) PR/merge policy.

**Exploration finding that reframes the task:** ~70% of this already exists — it is *fragmented and
unenforced*, not absent.

- **PR/merge policy** already lives in `docs/team-development.md` (branching, PR lifecycle, per-path required
  checks, cross-service ownership, WIP-limit-2, squash-merge, rebase-not-merge, quality gates).
- **Actions are already separated** by path-filtered `<component>-tests.yml` + tag-triggered
  `release-<component>.yml` + `release-please` per-component tags (`desktop-v*`, `server-v*`, `aigateway-v*`).
- **Run-from-source / branch / commit conventions** live in root `CONTRIBUTING.md`.

The problem at 10 devs is therefore **fragmentation + contradiction + no machine enforcement**:
- Root `CLAUDE.md` monorepo section is **stale** (lists `app/`, `cloud/`, `brand/`; references a non-existent
  `docs/devplan.txt`). Real layout is `apps/{server,desktop,aigateway,scoreboard}` + `web/`.
- Git-hooks path is documented two incompatible ways (`.githooks` vs husky `apps/desktop/.husky/_`); the active
  path is husky, which does **not** carry the "no direct commits to `main`" guard — so that guard is effectively
  off.
- Team roster differs between `CLAUDE.md` and the `project-knowledge` skill.
- **No `CODEOWNERS`, no PR template, no merge queue, no concurrency groups** on test workflows.
- `apps/scoreboard` is excluded from both `release-please` and `dependabot`.
- `project-knowledge/SKILL.md` has **no frontmatter**, so Claude can't auto-discover it.

**Intended outcome:** one discoverable guidance skill that *routes* (not duplicates), a thin machine-enforcement
layer that actually protects `main`, and a single canonical process doc that the skill + all `CLAUDE.md` files
point to.

## Assumptions (defaults chosen — veto any before we start)

The three scope questions went unanswered; proceeding on these defaults:

1. **Scope = Skill + Enforcement + Consolidation** (the full three layers below).
2. **Packages = polyglot component model (python/go/js/ts).** Per user directive, the monorepo model is
   documented as a **stack-agnostic component contract**, not a hardcoded list of today's apps. Define both
   `apps/<name>` (deployables) and `packages/<name>` (shared libs) as first-class, each of which may be
   Python, Go, JS, or TS. This change **defines the convention** (directory taxonomy + per-stack toolchain/CI/
   release contract) in the skill and canonical doc; it does **not** scaffold real shared libraries or migrate
   the duplicated Python pins yet (that's a follow-up ticket). Note the DRY smell (`tortoise-orm[asyncpg]==1.1.7`
   pinned independently across the Python apps) as the first candidate for a future `packages/py-*`.
3. **Branch protection = ownership unknown → verify first.** The plan configures what we can and *documents the
   desired branch-protection/merge-queue config as a request* if we don't hold admin.

## Guiding principle

**Single source of truth. The skill and every `CLAUDE.md` are pointers, never copies.** Any policy statement
lives in exactly one file. This is the whole point — a sixth document that restates the other five is a
regression.

---

## Layer 1 — Guidance skill (Claude-facing router)

**Create `.claude/skills/working-in-this-repo/SKILL.md`** with proper triggering frontmatter
(`name`, `description`, `user_invocable: true`). Description must fire on: "which app / where does this go /
what CI runs / who reviews / how do I branch/commit/PR/release here."

Content is a **router**, not a manual:
- **Component taxonomy (stack-agnostic):**
  - `apps/<name>` — an independently deployable service/app (has a release lane + image/installer).
  - `packages/<name>` — a shared library consumed by ≥2 components, **not** independently deployed. (None exist
    today; the convention is defined so a future shared lib in any stack lands cleanly.)
  - `web/` — static site (no build toolchain).
- **Current-apps router table** — one row per `apps/{server,desktop,aigateway,scoreboard}` + `web/`: path ·
  stack · run/test/lint/typecheck (the `make` target) · gating CI workflow · owner/reviewer · release lane
  (release-please component vs manual `scoreboard-v*` tag) · gotchas (aigateway no-Enterprise guard, credential
  storage).
- **Polyglot per-stack contract** — the invariant every new component must satisfy, one row per stack:

  | Stack | Pkg manager | Layout | Lint | Typecheck | Test | CI pattern | Release lane |
  |-------|-------------|--------|------|-----------|------|-----------|--------------|
  | Python | uv + hatchling | `src/<pkg>/` | ruff | pyright | pytest (+ markers) | copy `aigateway-tests.yml` | release-please `python`, or manual tag |
  | JS/TS | npm | `src/` | eslint | `tsc --noEmit` | vitest | copy `desktop-tests.yml` | release-please `node`, or manual tag |
  | Go | go modules | `cmd/` + `internal/`/`pkg/` | golangci-lint | `go vet` / build | `go test ./...` | new `go-<comp>-tests.yml` | release-please `go`, or manual tag |

- **"Adding a new component (any stack)" checklist** — the 7 things that make it visible to the coordination
  machinery: (1) pick `apps/` vs `packages/`; (2) self-contained toolchain + lockfile, no dep on another app's
  internals (depend only via `packages/`); (3) add a path-filtered `<component>-tests.yml`; (4) register a
  release lane (or mark "not released"); (5) add a CODEOWNERS entry; (6) add the matching dependabot ecosystem
  (uv/npm/gomod); (7) wire into the root `Makefile`.
- **"Which layer does my change belong to?"** — core vs plugin decision per the hexagonal rules already in
  `CLAUDE.md` (core must not import plugins); route new gateway behavior to active frontend plugins, never the
  deprecated intercept shims.
- **5-second branch/commit/PR/merge rules** inline, each linking to the canonical doc for the full version.
- Explicit links to `docs/team-development.md`, `CONTRIBUTING.md`, per-app `CLAUDE.md`.

Decide `project-knowledge/SKILL.md`'s fate: **merge it into this skill** (preferred) or give it frontmatter so
it's discoverable. Do not leave two overlapping knowledge skills.

## Layer 2 — Machine enforcement

- **`.github/CODEOWNERS`** — encode the informal ownership from `docs/team-development.md`:
  `apps/server/**` + `apps/desktop/**` → Sergey; `apps/aigateway/**` + `apps/scoreboard/**` + `web/portal/**` →
  Dmitry; root/`docs/**`/`.github/**` → both. Enables auto review-request routing.
- **`.github/pull_request_template.md`** — Asana permalink, summary, **which app(s) touched**, test plan,
  screenshots, and a path-aware checklist (ran the relevant `make` checks; ran `make test-aigateway-live` if
  gateway request/refresh changed).
- **Concurrency groups** added to each `<component>-tests.yml`:
  `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` — kills wasted CI
  on rapid re-pushes (10 devs = many rapid pushes). Do **not** add to release workflows.
- **Hooks fix** — the active hooksPath is husky. Fold the `.githooks/pre-commit` "no commits to `main`" guard
  into `apps/desktop/.husky/pre-commit`, and correct `CONTRIBUTING.md` (stop instructing `git config
  core.hooksPath .githooks`, which silently disables the husky suite). Note in the skill that hooks are
  local-only; server-side protection is branch protection.
- **Branch protection & merge queue** — verify admin access first. If we control it: require the per-path check
  names, require branch up-to-date, enable **merge queue**. If org-owned: write the desired config as a request
  in `docs/team-development.md`.

> **⚠ Gotcha to design around (this bites hard at 10 devs):** GitHub branch-protection **required checks +
> path-filtered workflows deadlock**. A required check whose workflow is skipped (paths didn't match) never
> reports success, so the PR can never merge. Two viable fixes — pick one in implementation:
> (a) a tiny always-runs "changes-detected" dispatcher job per component that reports the required status, or
> (b) rely on **merge queue**, which treats a skipped required check as passing. This choice is load-bearing;
> flag it explicitly when we implement.

## Layer 3 — Consolidation (delete & point)

- Designate **`docs/team-development.md` as the single canonical process doc.**
- **Fix root `CLAUDE.md`** — replace the stale monorepo section with the real `apps/*` + `web/` layout; drop the
  `docs/devplan.txt` / `app/` / `cloud/` / `brand/` references; add one-line pointers to the canonical doc and
  the new skill.
- **Reconcile team rosters** across `CLAUDE.md` and `project-knowledge` (include Dmitry, Kyle consistently).
- **Close the scoreboard drift** — add `apps/scoreboard` to `release-please-config.json` +
  `.github/dependabot.yml`, **or** add a one-line "intentionally manual" note explaining the exclusion.
- **Typecheck consistency** — either add `pyright` to `server-tests.yml`, or document that `pre-commit.yml` is
  the authoritative server typecheck gate (today it's implicit).
- **Resolve the stray `.claude/wf-sf295-300.js`** (untracked stacked-PR orchestration script) — move to a
  `.claude/workflows/` dir or `scripts/`, or delete. Decide whether stacked PRs are a sanctioned pattern and, if
  so, add one line to the canonical doc.

## Files to create / modify (representative)

**Create:** `.claude/skills/working-in-this-repo/SKILL.md`, `.github/CODEOWNERS`,
`.github/pull_request_template.md`.

**Modify:** root `CLAUDE.md` (destale), `docs/team-development.md` (canonical + branch-protection config),
`CONTRIBUTING.md` (hooks correction), `.github/workflows/{server,aigateway,desktop,scoreboard}-tests.yml`
(concurrency), `apps/desktop/.husky/pre-commit` (main-guard), `release-please-config.json` +
`.github/dependabot.yml` (scoreboard), `.claude/skills/project-knowledge/SKILL.md` (merge or add frontmatter).

## Out of scope (this change)

- Introducing a shared `packages/` layer or a JS workspace (turbo/nx/pnpm) — assessment only, no code.
- Rewriting per-app `CLAUDE.md` guardrails (aigateway secrets, server plugin contract) — the skill routes to
  them unchanged.
- Any change to the deprecated intercept plugins.

## Verification

- **Skill fires & routes:** in a fresh Claude Code session ask "where do I add an aigateway route / which CI
  runs for a desktop-only PR / who reviews `apps/server` changes / how do I cut a scoreboard release" — confirm
  the skill triggers and each answer matches the canonical doc.
- **CODEOWNERS:** open a draft PR touching `apps/server/**`; confirm the correct owner is auto-requested.
- **Required checks ≠ deadlock:** open a docs-only PR (no app paths) and confirm it can still merge under the
  chosen dispatcher/merge-queue approach.
- **Concurrency:** push twice quickly to a branch; confirm the first component-test run is cancelled.
- **Hooks:** attempt `git commit` on `main`; confirm it's blocked under the active (husky) path.
- **De-stale:** `grep -rn "devplan.txt\|^app/\|cloud/" CLAUDE.md` returns nothing; roster matches across files.

## Sequencing

1. Create SF-{n} ticket + branch (per repo rule; ask for/create Asana ticket before first commit).
2. Mirror this plan to `docs/superpowers/plans/` per the repo planning convention (plan-mode currently restricts
   edits to this plan file).
3. Layer 3 consolidation first (removes contradictions before we point at anything).
4. Layer 1 skill (points at the now-clean canonical doc).
5. Layer 2 enforcement (CODEOWNERS, PR template, concurrency, hooks, branch protection).
6. Verify per above; run relevant `make` checks; open PR.
