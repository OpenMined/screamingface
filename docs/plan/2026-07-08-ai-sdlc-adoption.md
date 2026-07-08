# AI SDLC Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the Linear-based AI SDLC per `docs/spec/2026-07-08-ai-sdlc-adoption-spec.md` — work items as `OME-N` in the existing Engineering team under the 😱 ScreamingFace V1 project, an `app/*`/`pkg/*`/`com/*` label matrix, repo-local skills/cards/agents/scripts, mandatory docs artifacts.

**Architecture:** One ID sequence (`OME-N`, existing team — D2); labels place the work (D10) with the mandatory `actor` group agentic|human (D13); STOPs are labels, not states (D12); every item attaches to the ScreamingFace V1 project (D11). Two committed cards parameterize four skills, two agents, and two scripts adapted from the installed sdlc plugin.

**Tech Stack:** Linear MCP plugin (the ONLY Linear transport — D4; API tokens/GraphQL forbidden), markdown skills/cards, Python (uv, PEP-723) scripts, GitHub Actions.

**Source plugin (copy-from):** `SRC=/Users/sergey/.claude/plugins/cache/socket0-claude/sdlc/0.1.0`
**Spec:** `docs/spec/2026-07-08-ai-sdlc-adoption-spec.md` (decisions D1–D13)

**Terminology (binding for all authored text):** ONE team; every work item is `OME-N`.
Labels place the work. "Team" appears only where it names the Linear object.

---

### Task 0: Preconditions — DONE 2026-07-08

- [x] **Linear MCP activated in Claude** — `/mcp` → `plugin:linear:linear` authenticated. This is THE precondition: ALL Linear operations go through MCP tools (`save_issue`, `save_comment`, `create_issue_label`, `list_*`). **API tokens / raw GraphQL are FORBIDDEN**; operations the MCP cannot perform (label delete, team create, workflow states) are OWNER actions in the Linear UI.
- [x] Source plugin present at `$SRC`.
- [x] Workspace facts confirmed: team **Engineering** key `OME` id `5f4d721f-4452-4ed1-990a-7cdbcd923508`; project **😱 ScreamingFace V1** id `7cbe5759-cc07-476d-b81e-da05b6b2d4d7` (slug `screamingface-v1-27666092fc7f`); states Todo `88de5fec…` / In Progress `03621515…` / In Review `62b4c1a3…` / Done `699b96ac…` / Triage `a6fc6a19…` (full map in `.docs/linear-bootstrap-ids.md`).

### Task 1: Linear bootstrap — labels — **DONE 2026-07-08 (taxonomy LOCKED: align + extend)**

- [x] Taxonomy locked (D10): existing `Epic` group children = workstream axis; existing `blocked ⛔` reused; plain `Bug`/`Feature`/`Improvement` reused for type-ish tagging.
- [x] Labels in place (survivors of the earlier trial, now canonical): `actor` group (agentic/human — D13), `who-acts` group (design-session/autonomous/deferred), `app/aigateway`, `app/scoreboard`, `pkg/url4-python-sdk`, `repo`, `needs-owner`. (`app/desktop`, `app/cli` wait for name lock — spec §7.)
- [x] IDs recorded in `.docs/linear-bootstrap-ids.md` (source for Task 3's card).
- [ ] **Owner UI cleanup:** delete obsolete trial labels — `com/url4`, `com/evalstudio`, `com/ensemble`, `com/credentials`, the `type` group (children task/decision), plain `blocked`.

### Task 2: Adoption epic + sub-issues — FILED 2026-07-08

- [x] **Epic `OME-358`** + sub-issues `OME-359` (cards+docs+CLAUDE.md), `OME-360` (skills), `OME-361` (agents+scripts+CI), `OME-362` (backfill, deferred) — team Engineering, project 😱 ScreamingFace V1, labels `repo`+`agentic`+`autonomous`, priority High. Everywhere below, `OME-E` = **OME-358**.
- [ ] **Step 2.2: Branch**

```bash
git checkout main && git pull --ff-only && git checkout -b OME-E-ai-sdlc-adoption
```
(Substitute the epic's real number.) NOTE: this PR bootstraps the convention it documents — deliberate one-time exception; state it in the PR body.

- [ ] **Step 2.3:** Epic → In Progress via MCP: `save_issue {id: "OME-E", state: "In Progress"}`.

---

### Task 3: The two cards

**Files:** Create: `.claude/task-board.local.md`, `.claude/sdlc.local.md`

- [ ] **Step 3.1: Write `.claude/task-board.local.md`** (IDs from `.docs/linear-bootstrap-ids.md`):

```markdown
---
system: linear
workspace: openmined
transport: "Linear MCP plugin (plugin:linear) — the ONLY transport; PRECONDITION: activate via /mcp. API tokens/GraphQL FORBIDDEN; MCP-uncovered ops are owner UI actions"
team: { key: OME, name: Engineering, id: "5f4d721f-4452-4ed1-990a-7cdbcd923508" }
project: { name: "😱 ScreamingFace V1", slug: screamingface-v1-27666092fc7f, id: "7cbe5759-cc07-476d-b81e-da05b6b2d4d7" }
states: { todo: "<id>", in_progress: "<id>", in_review: "<id>", done: "<id>", triage: "<id>" }
labels:
  epic_group:   # existing workstream axis (one per issue) — adopted as-is (D10)
    url4-engine: "<id>", ai-gateway: "<id>", eval-runner-datasets: "<id>", results-runs: "<id>",
    leaderboard: "<id>", auth-subsidized-compute: "<id>", desktop-app: "<id>", python-sdk: "<id>",
    multi-turn-ensembles: "<id>", sota-hunt: "<id>", compute-budgeting: "<id>"
  landing: { app/aigateway: "<id>", app/scoreboard: "<id>", pkg/url4-python-sdk: "<id>", repo: "<id>" }  # app/desktop, app/cli at name lock
  stop: { blocked: "<blocked ⛔ id>", needs-owner: "<id>" }   # D12: labels + comment, not states
  who_acts: { group: "<id>", design-session: "<id>", autonomous: "<id>", deferred: "<id>" }
  actor: { group: "<id>", agentic: "<id>", human: "<id>" }    # D13: MANDATORY, one per item
  type_ish: { bug: "<Bug id>", feature: "<Feature id>", improvement: "<Improvement id>" }  # existing plain labels, optional
priority: { P1: 2, P2: 3, P3: 4 }   # Linear ints: 1 urgent (incidents only)
close_template: |
  Commits: <sha> <message>[, …]
  Gates: <run_gates.py summary / test counts>
  Ledger: docs/work/<file>.md
  Deviations: <none | list>
  Owner-verify: <none | what to check visually>
---

# Ticket rules (bind alongside the task-management skill)

- Every work item: team Engineering + project 😱 ScreamingFace V1 (D11) + exactly one
  `type` label + one `who-acts` label + one `actor` label (agentic|human — D13, mandatory).
- Labels place the work: `app/*`/`pkg/*` = WHERE (multi-value), `com/*` = product component
  (open set — PRODUCT concepts, never internal modules), `repo` = process work (no app/pkg).
- D9: ≥2 app/pkg labels → cross-component epic (`com/X` + all affected labels) with one
  sub-issue per affected app/package. Never a single-app filing, never one mega-ticket.
- D12 STOPs: apply `blocked` or `needs-owner` label + comment stating the exact question;
  issue stays In Progress; remove the label when resolved. Never add states to the shared team.
- MCP quirk: `save_issue.labels` REPLACES the whole set — read current labels, resend the
  union. Relations (blockedBy/relatedTo) are append-only.
- New app/package/component ⇒ its label created AND registered here in the same change.
- Every work item gets a mirror `docs/tasks/YYYY-MM-DD-<name>.md` at create; status closed
  in BOTH Linear and the mirror at finish. Linear is the status authority.
- A dev item descending from a product/marketing Asana task carries the Asana URL in its
  description (`asana_url` in the mirror frontmatter). Technical work NEVER goes to Asana.
```

- [ ] **Step 3.2: Write `.claude/sdlc.local.md`** — unchanged from spec §3.2:

```markdown
---
stacks:
  - name: aigateway
    root: apps/aigateway
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run python scripts/check_no_enterprise.py
      - uv run pytest --cov=aigateway --cov-fail-under=80 -q
  - name: scoreboard
    root: apps/scoreboard
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run pytest --cov=scoreboard --cov-fail-under=80 -q
commit_refs: "Refs: OME-N"
extra_anchors: []
companion_skills:
  - skill: tortoise-dev
    when: "models/ or migrations/ touched in a python stack"
    mandatory: true
ledger_dir: docs/work/
---

# Stack conventions

## aigateway (python)
- INVARIANTS: credentials only via ORMStore/`credential_blobs` (AES-256-GCM through
  SecretStoreMixin); no OS keychain; `AIGATEWAY_SECRET_KEY` never stored/logged; never
  import litellm-enterprise (gate-guarded).
- Providers/secrets backends implement the port + register in the factory; never edit ORMStore.

## scoreboard (python)
- INVARIANTS: public artifact allowlist in `src/scoreboard/portal.py` (PUBLIC_ARTIFACTS /
  FORBIDDEN_ARTIFACTS); portal + artifacts stay app-local (`portal/`, `artifacts/`).

## ledger naming (D8)
`docs/work/YYYY-MM-DD-<ticket-id>-<short-description>.md` — created at work START
(date = start), frontmatter `status: planned|in_progress|done` + `finished:` filled at close.
Template: copy docs/work/TEMPLATE.md.
```

- [ ] **Step 3.3: Commit**

```bash
git add .claude/task-board.local.md .claude/sdlc.local.md
git commit -m "feat(OME-E): add task-board + sdlc cards (Linear registry, stack gates)" -m "Refs: OME-E"
```

---

### Task 4: docs tree + dogfood mirror/ledger

**Files:**
- Create: `docs/tasks/`, `docs/work/`; `docs/work/TEMPLATE.md` (copy `$SRC/templates/work-ledger/TEMPLATE.md`)
- Modify: `docs/README.md` (mark tasks/work as live)
- Create: `docs/tasks/2026-07-08-ai-sdlc-adoption.md`, `docs/work/2026-07-08-OME-E-ai-sdlc-adoption.md`

- [ ] **Step 4.1:** `mkdir -p docs/{tasks,work}`; `cp $SRC/templates/work-ledger/TEMPLATE.md docs/work/TEMPLATE.md`.
- [ ] **Step 4.2:** In `docs/README.md` drop the "(arrive with the AI SDLC implementation)" qualifiers.
- [ ] **Step 4.3:** Mirror `docs/tasks/2026-07-08-ai-sdlc-adoption.md`:

```markdown
---
id: OME-E
linear_url: <epic url>
status: in_progress
type: epic
priority: P1
labels: [repo, agentic, autonomous]
created: 2026-07-08
closed:
---
Adopt the Linear AI SDLC per docs/spec/2026-07-08-ai-sdlc-adoption-spec.md.
```
Ledger `docs/work/2026-07-08-OME-E-ai-sdlc-adoption.md`: from TEMPLATE, Intent/Planned/Test plan/Acceptance from this plan; Outcome at close.

- [ ] **Step 4.4: Commit** — `git add docs && git commit -m "feat(OME-E): docs tasks/work tree + dogfood mirror and ledger" -m "Refs: OME-E"`

---

### Task 5: CLAUDE.md — AI SDLC section

**Files:** Modify: `CLAUDE.md`

- [ ] **Step 5.1:** DELETE sections `## Git Workflow` (incl. subsections) and `## Planning Tickets`. INSERT the spec §4 rules VERBATIM (rules 0–7: 95% gate top rule; work item first — Engineering team + ScreamingFace V1 project + labels incl. one `actor` agentic|human; work ledger; spec-before-plan-before-code; diagramming plugin + docs/diagrams; branches `OME-N-<desc>` + `Refs: OME-N`, no Co-Authored-By, never commit to main; Asana read-only boundary; D9 cross-cutting rule).
- [ ] **Step 5.2:** Commit: `git add CLAUDE.md && git commit -m "feat(OME-E): replace Asana git workflow with AI SDLC rules" -m "Refs: OME-E"`

---

### Task 6: `asana-product` skill (read-only transform)

**Files:** Create: `.claude/skills/asana-product/SKILL.md`

- [ ] **Step 6.1:** Author from `~/.claude/skills/asana/SKILL.md`: keep the API-access block (PAT discovery, curl pattern, URL parsing) VERBATIM and the read operations (`my tasks`, `workspaces`, `projects`, `tasks <gid>`, `task <gid>`, `search`, `sections`). DELETE `create`, `update`, `complete`, `move`. Frontmatter description: "Read-only view of product/marketing top-level tasks in Asana. NEVER creates or updates anything in Asana." Add the Hard rules block (read-only; Asana = source, never destination; `asana_url` linkage — spec §2.1).
- [ ] **Step 6.2:** Commit: `git add .claude/skills/asana-product && git commit -m "feat(OME-E): asana-product read-only skill" -m "Refs: OME-E"`

---

### Task 7: `task-management` skill — Linear rewrite (MCP-first)

**Files:** Create: `.claude/skills/task-management/SKILL.md`

- [ ] **Step 7.1:** Author using `$SRC/skills/task-management/SKILL.md` as the structural source, per spec §2.2: announce line "Using the task-management skill — the Linear work-item lifecycle."; card-resolution HARD STOP; lifecycle; batching; mid-session-discovery; close discipline; anti-pattern table with label-discipline rows. Transport section: **MCP tools first** (`save_issue`, `save_comment`, `list_issues`, `list_issue_labels`, `create_issue_label`; team/project/labels/state by NAME, priority ints), with these encoded quirks: `labels` REPLACES the set (read-modify-write); relations append-only; every create sets `team: Engineering` + `project: 😱 ScreamingFace V1` + one type + one who-acts + one actor label. No token/GraphQL usage anywhere — MCP only; uncovered ops go to the owner (D4). D12 STOP mechanics (label + comment). 

- [ ] **Step 7.2: Include this "Linear rich text" reference section VERBATIM in the skill** (research 2026-07-08 — sources: [Editor docs](https://linear.app/docs/editor), [collapsible changelog](https://linear.app/changelog/2025-03-19-collapsible-sections), MCP tool contracts):

````markdown
## Linear rich text — the markdown dialect for descriptions & comments

Linear converts Markdown to its rich-text editor model. When writing via API/MCP:

- **Send raw markdown with literal newlines — NEVER escape sequences** (`\n` arrives as
  two characters). The MCP tools state this contract explicitly.
- **Headings:** `#`–`####` (H1–H4). Deeper levels don't exist.
- **Text:** `**bold**`, `_italic_`, `~~strike~~`, `` `inline code` ``. Underline has NO
  markdown syntax (editor-only Cmd/Ctrl U) — don't try.
- **Lists:** `-`/`*`/`+` bullets, `1.` numbered, `- [ ]` / `[]` checklists; all nestable.
  Checklists in a description render as interactive checkboxes — good for acceptance lists.
- **Blockquote:** `>` … · **Collapsible section:** `+++ Title` on its own line, content,
  closing `+++` (nestable) — use for long logs/gate output in close comments.
- **Code:** fenced ``` blocks with language tag; ` ```mermaid ` renders a Mermaid diagram.
- **Divider:** `---` on its own line. **Tables:** GFM pipe tables render as Linear tables —
  keep them simple (no spans).
- **Emoji:** `:name:` (`:warning:` etc.).
- **Mentions — SIDE-EFFECTS:** `@displayName` mentions a user → notifies + subscribes them
  (MCP contract). Issue references auto-link aggressively: `@OME-123`, pasted issue URLs,
  AND **bare `OME-123` identifiers in plain prose** all get converted to issue embeds
  (verified live 2026-07-08) and can create "related to" relations. When no link/relation
  is wanted, wrap the ID in backticks — code spans are left alone.
- **Embeds:** bare YouTube/Loom/Figma/Google-Docs URLs auto-embed. To keep a plain link,
  wrap it in standard `[text](url)` markdown.
- **No HTML.** Raw HTML is not rendered — write markdown only.
- Copy an issue back out as markdown via the in-app command `copy issue in markdown`.
````

- [ ] **Step 7.3:** Commit: `git add .claude/skills/task-management && git commit -m "feat(OME-E): task-management skill — Linear MCP lifecycle + rich-text reference" -m "Refs: OME-E"`

---

### Task 8: `sdlc-python` + `sdlc-react` skills

**Files:** Create both from `$SRC/skills/<name>/SKILL.md`

- [ ] **Step 8.1:** `cp` both, then IDENTICAL edits in the SHARED-LOOP regions of BOTH:
  1. Rule 7 runner path → `uv run .claude/scripts/run_gates.py <stack>` (drop the plugin-root parenthetical).
  2. Rule 1 ledger → `(copy docs/work/TEMPLATE.md; this repo: docs/work/, named YYYY-MM-DD-<ticket-id>-<desc>.md per D8)`.
  3. Sibling references: name only the adopted pair; drop `sdlc-go` mentions.
- [ ] **Step 8.2:** Stack sections stay verbatim.
- [ ] **Step 8.3:** Parity check green (Task 10 script). Commit: `git add .claude/skills/sdlc-* && git commit -m "feat(OME-E): sdlc-python + sdlc-react rigid-loop skills" -m "Refs: OME-E"`

---

### Task 9: Agents

**Files:** Create both from `$SRC/agents/<name>.md`

- [ ] **Step 9.1:** `sdlc-unit-executor.md` edits: input = "Linear identifier (`OME-N`)"; reads via Linear MCP per the card; STOP table's "Board move" column → "apply `blocked` (or `needs-owner`) label + comment via MCP `save_issue`/`save_comment`" (D12 — issue stays In Progress); drop `sdlc-go`; JSON contract `"ticket": "<OME-N>"`.
- [ ] **Step 9.2:** `ticket-filer.md` edits: entries `title, body, labels, priority, type, actor, parent?`; validate against the card registry incl. **actor mandatory (D13)** — missing actor label → all-or-nothing reject; files via MCP `save_issue` (team + project from card); returns `identifier | title | URL | state`.
- [ ] **Step 9.3:** Commit: `git add .claude/agents && git commit -m "feat(OME-E): sdlc-unit-executor + ticket-filer agents (Linear MCP)" -m "Refs: OME-E"`

---

### Task 10: Scripts

- [ ] **Step 10.1:** `cp $SRC/scripts/run_gates.py .claude/scripts/run_gates.py` (verbatim); smoke-test: `uv run .claude/scripts/run_gates.py aigateway` and `… scoreboard` → ALL GATES GREEN.
- [ ] **Step 10.2:** Write `.claude/scripts/check_loop_parity.py` — the plugin's parity script with `ROOT = pathlib.Path(__file__).resolve().parent.parent`, `SKILLS = ["sdlc-python","sdlc-react"]`, `path = ROOT / "skills" / name / "SKILL.md"`; rest byte-identical.
- [ ] **Step 10.3:** `python3 .claude/scripts/check_loop_parity.py` → `LOOP PARITY OK …`.
- [ ] **Step 10.4:** Commit: `git add .claude/scripts && git commit -m "feat(OME-E): run_gates + loop-parity scripts" -m "Refs: OME-E"`

---

### Task 11: CI — `repo-checks.yml`

- [ ] **Step 11.1:** Create `.github/workflows/repo-checks.yml`:

```yaml
name: Repo Checks
on:
  push:
    paths: [".claude/skills/sdlc-**", ".claude/scripts/**", ".github/workflows/repo-checks.yml"]
  pull_request:
    paths: [".claude/skills/sdlc-**", ".claude/scripts/**", ".github/workflows/repo-checks.yml"]
  workflow_dispatch:
permissions: { contents: read }
jobs:
  loop-parity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SHARED-LOOP parity
        run: python3 .claude/scripts/check_loop_parity.py
```

- [ ] **Step 11.2:** Commit: `git add .github/workflows/repo-checks.yml && git commit -m "ci(OME-E): loop-parity check on sdlc skill changes" -m "Refs: OME-E"`

---

### Task 12: `working-in-this-repo` skill update

- [ ] **Step 12.1:** §6: `SF-{n}` branch rule → `OME-N-<desc>` ("N = the Linear number; registry `.claude/task-board.local.md`"); commit body `Refs: OME-N`. Routing table: add `Label` column (`app/aigateway`, `app/scoreboard`). §7 pointers: add `task-management`, `sdlc-*` skills, both cards.
- [ ] **Step 12.2:** Commit: `git add .claude/skills/working-in-this-repo && git commit -m "docs(OME-E): route working-in-this-repo to Linear SDLC" -m "Refs: OME-E"`

---

### Task 13: Verification sweep

- [ ] **Step 13.1:** Parity OK; both `run_gates.py` stacks GREEN.
- [ ] **Step 13.2:** Stale-reference grep:

```bash
git grep -nE 'SF-\{n\}|Asana ticket|asana permalink|docs/plans/|docs/specs/|AAGW-|C-team|C-prefix|OM-N|1213703035415126' -- . ':!docs/plan' ':!docs/spec' ':!.docs'
```
Expected: zero hits (spec/plan narrate history; they're excluded).
- [ ] **Step 13.3:** MCP dry-run: create a throwaway issue (team Engineering, project ScreamingFace V1, labels `repo`+`task`+`autonomous`+`agentic`), verify the `type`/`actor` groups reject a second label from the same group, move Todo→In Progress→Done with a close comment, then delete it in the Linear UI (MCP has no delete tool).

---

### Task 14: Ledger outcome, PR, close discipline

- [ ] **Step 14.1:** Fill ledger Outcome; mirror + ledger `status: done` / `closed:` date.
- [ ] **Step 14.2:** Push, open PR `feat(OME-E): adopt Linear AI SDLC (skills, cards, agents, scripts, CI)`; body: summary, epic URL, test plan, bootstrap-exception note, "supersedes SF-N/Asana workflow".
- [ ] **Step 14.3:** After CI green + review + squash-merge: close sub-issues then the epic with the card's `close_template` filled (use a `+++ Gates +++` collapsible for gate output); file backfill items (all with `actor` labels): `repo`+`human`: "Lock package names + reserve (pypi/npm/brew)" (design-session), "GitHub Pages: keep frozen vs disable" (design-session); `app/scoreboard`+`agentic`: "Portal vendoring stopgap — revisit with web story" (deferred); `pkg/url4-python-sdk`+`com/url4`+`agentic`: "Extract url4 SDK from legacy tag" (epic).

---

## Self-review

- Spec coverage: D1/D2 → Tasks 0–2 (done) + 3; D3 → 6; D4 → Task 0 + Task 7 transport; D5 → 8/10; D6/D8 → 4; D7/D9 → cards + CLAUDE.md (5); D10/D13 → Task 1 (done) + card + filer validation (9.2); D11 → card + every save_issue; D12 → card + executor STOP table (9.1); §5 → 9–11; §2.4 → 12; §6 phase 5 → 14.3. Rich-text research → Task 7.2 verbatim block.
- No placeholders beyond `<id>/OME-E` slots produced by Tasks 0–2 (recorded in `.docs/linear-bootstrap-ids.md`).
- Naming consistent: `Refs: OME-N`, label namespaces `app/ pkg/ com/`, groups `type`/`who-acts`/`actor`.
