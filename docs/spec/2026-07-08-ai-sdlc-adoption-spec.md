---
title: AI SDLC adoption — Linear work items, repo docs artifacts, per-stack skills
status: approved-design, pending-implementation
created: 2026-07-08
author: Sergey Bershadsky + Claude (Fable 5)
supersedes: Asana-based git workflow in CLAUDE.md (SF-N tickets)
related:
  - .docs/teardown-plan.md (SF-348, PR #371)
  - docs/diagrams/work-item-topology.png (+ .svg source)
  - https://github.com/sergio-bershadsky/ai/tree/main/plugins (source of sdlc/task-management artifacts)
---

# AI SDLC adoption — spec

## Context

After the SF-348 re-foundation, the repo hosts `apps/aigateway`, `apps/scoreboard`, and a
reserved `packages/` root, with new desktop/CLI packages incoming. Development process moves
from Asana-centric SF-N tickets to a repo-local AI SDLC: **Linear** as the dev work-item
system of record, mandatory in-repo artifacts (`docs/tasks`, `docs/work`, `docs/spec`,
`docs/plan`, `docs/diagrams`), and rigid per-stack SDLC skills adapted from the external
sdlc plugin (sergio-bershadsky/ai). Pasted plugin artifacts are adapted critically, not
copied verbatim.

## Decisions locked (2026-07-08)

| # | Decision | Choice |
|---|---|---|
| D1 | System of record | **Linear** is the single system of record for dev work items; the task-management skill runs on it. |
| D2 | Ticket IDs *(revised same day)* | **Single Linear team, key `OM`** — one global sequence `OM-N` for every work item (the Asana SF-N model). Per-component team keys (`AAGW-321` style) were evaluated and dropped: too heavy for ad-hoc work. No zero-padding (Linear cannot render it — verified; sources below). |
| D3 | Asana role | **Strictly read-only** source of product/marketing top-level tasks (list/read/search). Never create or update. Technical work items NEVER go to Asana. |
| D4 | Linear access | Workspace + API key exist. Key stored at `~/.config/linear/.env` as `LINEAR_API_KEY`. |
| D5 | Stack skills now | `sdlc-python` + `sdlc-react`. **`sdlc-go` deferred** until a Go component exists (YAGNI). |
| D6 | Docs dirs | `docs/tasks/`, `docs/work/`, `docs/spec/`, `docs/plan/`, `docs/diagrams/` (spec/plan singular — user decision, overriding the plural SF-348 landed; CLAUDE.md + docs/README.md updated at implementation). |
| D7 | Repo/process work *(revised)* | Plain **`repo`** label, no `app/*`/`pkg/*` label. (The earlier REPO catch-all team is obsolete under single-team D2.) |
| D8 | Ledger timing | Ledger file created at work **start** (`docs/work/YYYY-MM-DD-<ticket-id>-<desc>.md`, date = start), frontmatter `status: planned|in_progress|done` + `finished:` date at close. Reconciles "ledger-first" (sdlc rule 1) with "write ledger when finished" (user rule 2). |
| D9 | Cross-cutting work *(revised)* | Work spanning ≥2 apps/packages is **signed as a cross-app product component via labels**: `com/<component>` + every affected `app/*`/`pkg/*` label, filed as an **epic with one sub-issue per affected app/package**. (The interim C-prefix-team scheme is superseded by single-team D2.) |
| D10 | Label taxonomy | Namespaced full-name labels: `app/[name]`, `pkg/[name]`, `com/[name]` as **plain multi-value labels** (Linear label groups enforce one-per-issue and would break cross-cutting); `type` and `who-acts` as **Linear label groups** (one-per-issue enforcement wanted there). |

Linear ID research sources: [Linear conceptual model](https://linear.app/docs/conceptual-model),
[Teams](https://linear.app/docs/teams), [Creating issues](https://linear.app/docs/creating-issues),
[Labels](https://linear.app/docs/labels).

## 1. Work-item topology

**We are ONE team.** One Linear team (key **`OM`**) → every work item is `OM-N`, one global
sequence. WHERE the work lands and WHAT it affects live in **labels**, not in the ID:

| Namespace | Axis | Values (initial) |
|---|---|---|
| `app/[name]` | application the work lands in | `app/aigateway`, `app/scoreboard`; `app/desktop`, `app/cli` created at name lock |
| `pkg/[name]` | package the work lands in | `pkg/url4-python-sdk` |
| `com/[name]` | product component affected (open set) | `com/url4`, `com/evalstudio`, `com/ensemble`, `com/credentials` |
| `repo` | repo/process work (no app/pkg label) | — |
| `type` group | deliverable kind — ONE per issue | `type/epic`, `type/feature`, `type/bug`, `type/task`, `type/decision` |
| `who-acts` group | who moves it — ONE per issue | `design-session`, `autonomous`, `deferred` |

Mechanics:
- `app/*`, `pkg/*`, `com/*` are **plain namespaced labels** — an issue may carry several
  (required for cross-cutting epics). `type` and `who-acts` are **Linear label groups**, so
  Linear itself enforces one-per-issue.
- `com/*` names are PRODUCT concepts, never internal modules. New app/package/component ⇒
  its label registered in the card **in the same change** that introduces it.
- Priority: Linear's native field (card maps P1→High(2), P2→Medium(3), P3→Low(4); Urgent(1)
  reserved for incidents).
- Workflow states (one set, one team): `Todo → In Progress → Blocked → Needs Owner → Done`
  (+ built-ins Backlog/Canceled). `Blocked`/`Needs Owner` are the unit-executor STOP targets.
- Epics = Linear parent issues with sub-issues; milestones = Linear projects (one per plan
  doc that decomposes into 3+ work items).

**Cross-cutting rule (D9):** ≥2 `app/*`/`pkg/*` labels ⇒ the work is cross-component: file an
**epic** carrying `com/<component>` + all affected `app/*`/`pkg/*` labels, with **one
sub-issue per affected app/package** (one SDLC unit each; each sub-issue carries its own
`app/*`/`pkg/*` label + the same `com/*` label). Never one mega-ticket, never filed as if it
were single-app work.

**Registry card:** `.claude/task-board.local.md` — **committed** (repo config, not personal).
Contains: workspace slug, team key+ID, state name→ID map, label registry (all namespaces +
group IDs), priority map, close-comment template, key source path. Card missing → HARD STOP
(same rule as the source skill).

## 2. Skills (repo-local, `.claude/skills/`)

### 2.1 `asana-product` (transform of the global asana skill)
- Operations kept: list projects/tasks, read task, search, parse URLs.
- Operations REMOVED: create, update, complete, move, sections-add.
- Hard rules in skill text: Asana is a read-only source of product/marketing top-level tasks
  defined by product/marketing tooling; NEVER create any ticket in Asana; NEVER mirror
  technical work there. A dev work item descending from a product task carries the Asana URL
  in its Linear description (`asana_url` in the docs/tasks mirror frontmatter).

### 2.2 `task-management` (Linear rewrite of the source skill)
Keeps verbatim-in-spirit: announce line, card-resolution HARD STOP, single-task-holder rule,
lifecycle (PLAN → TICKETS → owner ticket review → plan one ticket → implement via stack SDLC
→ close → next), batching, mid-session-discovery rule (file first, 30 seconds), close
discipline (commits + gates + ledger paths + deviations in a comment before Done),
anti-pattern table (GitHub-specific rows replaced with label-discipline rows, e.g. "filing
cross-cutting work with a single app label" → D9 STOP).
Changes:
- Command crib: Linear GraphQL via `curl` (`Authorization: <LINEAR_API_KEY>`), templated
  from the card: issueCreate, issueUpdate (state), commentCreate, issue search/filter by label.
- No retitle/code bookkeeping — Linear assigns `OM-N` natively.
- Affect matrix: **entirely labels** — `app/*`/`pkg/*` = WHERE (multi-value), `com/*` = WHAT;
  D9 epic/sub-issue discipline whenever WHERE has ≥2 values.
- Every work item gets a `docs/tasks/` mirror (see §4) — a repo-side record, not a second
  board: Linear stays the status authority; the mirror updates at create/close only.

### 2.3 `sdlc-python` and `sdlc-react` (adopted; `sdlc-go` deferred — D5)
- SHARED-LOOP regions kept **verbatim-identical** across the two adopted skills (loop parity
  enforced by script, §5).
- Adaptations (identical in both files): gate runner path
  `uv run .claude/scripts/run_gates.py <stack>` (no `${CLAUDE_PLUGIN_ROOT}` repo-locally);
  `ledger_dir` → `docs/work/` with D8 naming; ticket refs are `OM-N` (`Refs: OM-N` as the
  card's `commit_refs`); sibling references name only the adopted pair; project
  names/examples → this repo's.
- Stack idiom sections unchanged (python: migrations-with-schema S1, no bare except, no
  type:ignore; react: a11y gate S1, RTL behavior/roles, no `any` at boundaries).

### 2.4 `working-in-this-repo` (update, same change)
§6 branch/PR rules → Linear flow (branch `OM-N-<desc>`, `Refs: OM-N` in commit body);
pointers add task-management + sdlc-* skills and the two cards; routing table gains the
`app/*` label per app.

## 3. Cards

### 3.1 `.claude/task-board.local.md` (committed)
Frontmatter: `system: linear`, workspace, `team: {key: OM, id}`, states map (todo /
in_progress / blocked / needs_owner / done), label registry (`apps:`, `pkgs:`, `coms:`,
`repo:`, `types:` group, `who_acts:` group — name→ID), priority map,
`key_source: ~/.config/linear/.env`, `close_template`. Body: ticket rules (D9 label
discipline, Asana-URL rule, mirror-file rule, com-labels-are-product-concepts).

### 3.2 `.claude/sdlc.local.md` (committed)
Frontmatter `stacks:`:
- `aigateway` — root `apps/aigateway`, skill `sdlc-python`, gates: `uv run ruff check`,
  `uv run ruff format --check`, `uv run pyright`, enterprise-import guard,
  `uv run pytest --cov=aigateway --cov-fail-under=80`; `test_globs: ["tests/**"]`.
- `scoreboard` — root `apps/scoreboard`, skill `sdlc-python`, same pattern (`--cov=scoreboard`).
- (react/desktop stack entry added when the app lands.)
Body per stack: invariants (aigateway: credential encryption path, no OS keychain, no
litellm-enterprise; scoreboard: artifact allowlist/forbidden routes), `commit_refs: "Refs: OM-N"`,
`extra_anchors: []`, companion_skills (e.g. `tortoise-dev` for schema/migrations — mandatory).

## 4. Mandatory CLAUDE.md "AI SDLC" section (replaces "Git Workflow" Asana rules)

0. **95% confidence gate — TOP RULE.** Never write, assert, or implement anything you are
   not ≥95% confident is both correct AND wanted. Below 95% → STOP and ask first. Applies
   to every rule below and every artifact: code, work items, docs, diagrams.
1. **Work item first.** All work starts as a Linear issue (`OM-N`) carrying its labels
   (`app/*`/`pkg/*` or `repo`; `com/*` when a product component is affected; one `type/*`;
   one who-acts) plus a mirror `docs/tasks/YYYY-MM-DD-<name>.md` (frontmatter: id,
   linear_url, asana_url?, status, type, priority, labels, created, closed). At finish,
   close status in BOTH.
2. **Work ledger.** Every finished unit has `docs/work/YYYY-MM-DD-<ticket-id>-<desc>.md`
   (created at work start, outcome filled at finish — see the sdlc skills).
3. **Spec before plan, plan before code.** `docs/spec/` artifact required before planning;
   `docs/plan/` artifact required before implementation. Prefer/propose `/superpowers`
   (brainstorming → writing-plans) or similar. Never plan or implement without them.
4. **Diagrams.** Propose the diagramming plugin
   (https://github.com/sergio-bershadsky/ai/tree/main/plugins/diagramming) when it's absent;
   assets live in `docs/diagrams/` (SVG source + PNG).
5. **Branches/commits.** Branch `OM-N-<desc>` (e.g. `OM-12-fix-refresh`). Conventional
   commits; body carries `Refs: OM-N`; never `Co-Authored-By`; never commit to `main`.
6. **Asana boundary.** Asana is READ-ONLY product/marketing input (`asana-product` skill).
   Technical work items never go to Asana.
7. **Cross-cutting work (D9).** Touching ≥2 apps/packages → epic with `com/<component>` +
   all affected `app/*`/`pkg/*` labels, one sub-issue per affected app/package. Never a
   single-app filing, never one mega-ticket.

## 5. Agents & scripts

- `.claude/agents/sdlc-unit-executor.md` — executes ONE `OM-N` work item through the stack's
  SDLC loop; STOP conditions compile to Linear state moves (`Blocked` / `Needs Owner`) +
  comment; same JSON return contract and prohibitions as the source agent.
- `.claude/agents/ticket-filer.md` — validates every entry against the card's label/priority
  registry, then files via Linear GraphQL; all-or-nothing; returns
  `identifier | title | URL | state` table.
- `.claude/scripts/run_gates.py` — adopted near-verbatim (card-driven, PEP-723 uv script).
- `.claude/scripts/check_loop_parity.py` — `SKILLS = ["sdlc-python","sdlc-react"]`, paths
  under `.claude/skills/`; extended per stack added.
- `.github/workflows/repo-checks.yml` — path-filtered to `.claude/skills/sdlc-*/**` +
  `.claude/scripts/**`; runs loop-parity.

## 6. Implementation phases

1. **Bootstrap Linear** — create/confirm team `OM`; add `Blocked` + `Needs Owner` states;
   create labels (plain: `app/*`, `pkg/*`, `com/*`, `repo`; groups: `type`, `who-acts`);
   record IDs; verify key at `~/.config/linear/.env`. File the adoption epic (`type/epic`,
   `repo`, `autonomous`) with phase sub-issues.
2. **Cards + CLAUDE.md** — write both cards; replace CLAUDE.md Git-Workflow section with §4;
   update `working-in-this-repo`.
3. **Skills** — `asana-product`, `task-management` (Linear), `sdlc-python`, `sdlc-react`.
4. **Agents + scripts + CI** — §5 items; parity green.
5. **Backfill work items** — `repo`: name lock-down/reservation, GH Pages decision;
   `app/scoreboard`: portal stopgap revisit; `pkg/url4-python-sdk`: url4 SDK extraction epic
   (`app/desktop` / `app/cli` epics wait for name lock).

## 7. Out of scope / deferred

- `sdlc-go` (until a Go component exists — D5).
- `app/desktop` / `app/cli` labels and epics (until package names locked).
- Migration of historical Asana SF-N tickets into Linear (not requested).
- Linear MCP integration (curl/GraphQL chosen; MCP can replace transport later without
  changing the process).

## Open questions (none blocking)

- Exact Linear team/state/label IDs — resolved during phase 1 bootstrap.
- Whether `repo-checks.yml` also runs actionlint — nice-to-have, decide in implementation.

Confidence: ≥95% on design correctness/completeness given locked decisions D1–D10.
