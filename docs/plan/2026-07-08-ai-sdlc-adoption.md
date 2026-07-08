# AI SDLC Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the Linear-based AI SDLC per `docs/spec/2026-07-08-ai-sdlc-adoption-spec.md` — one Linear team (`OM-N` IDs) with an `app/*`/`pkg/*`/`com/*` label matrix as system of record, repo-local skills/cards/agents/scripts, mandatory docs artifacts.

**Architecture:** Single Linear team `OM` = one ID sequence; labels place the work (D10 taxonomy); two committed cards (`.claude/task-board.local.md`, `.claude/sdlc.local.md`) parameterize four skills (`asana-product`, `task-management`, `sdlc-python`, `sdlc-react`), two agents, and two scripts adapted from the installed sdlc plugin.

**Tech Stack:** Linear GraphQL API (curl), markdown skills/cards, Python (uv, PEP-723) scripts, GitHub Actions.

**Source plugin (copy-from):** `SRC=/Users/sergey/.claude/plugins/cache/socket0-claude/sdlc/0.1.0`
**Spec:** `docs/spec/2026-07-08-ai-sdlc-adoption-spec.md` (decisions D1–D10)

**Terminology (binding for all authored text):** ONE team, one sequence — every work item is
`OM-N`. `app/[name]`, `pkg/[name]`, `com/[name]` are plain multi-value labels; `type` and
`who-acts` are Linear label groups. "Team" appears only where it names the Linear API object
(`teamId`, `teamCreate`).

---

### Task 0: Preconditions

- [ ] **Step 0.1: Verify Linear API key**

```bash
export $(grep LINEAR_API_KEY ~/.config/linear/.env | xargs)
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { id name email } }"}' https://api.linear.app/graphql
```
Expected: JSON with viewer name/email. 401 → mint a key at linear.app → Settings → API, store as `LINEAR_API_KEY=lin_api_…` in `~/.config/linear/.env` (`chmod 600`).

- [ ] **Step 0.2: Verify source plugin present**

```bash
ls $SRC/skills/sdlc-python/SKILL.md $SRC/agents/sdlc-unit-executor.md $SRC/scripts/run_gates.py $SRC/templates/task-board.local.md
```
Expected: all four paths listed.

---

### Task 1: Linear bootstrap — team `OM`, states, labels

**Files:** Create: `.docs/linear-bootstrap-ids.md` (scratch, gitignored — IDs for Task 3)

- [ ] **Step 1.1: Create (or confirm) the team**

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
  "query": "mutation{ teamCreate(input:{name:\"OpenMined\",key:\"OM\"}){ team { id key name } } }"
}' https://api.linear.app/graphql
```
Expected: `team.id` UUID. Key already exists → `{"query":"{ teams { nodes { id key } } }"}` and reuse. Record the ID.

- [ ] **Step 1.2: Add `Blocked` and `Needs Owner` workflow states**

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
  "query": "mutation($t:String!,$n:String!,$c:String!){ workflowStateCreate(input:{teamId:$t,name:$n,type:\"started\",color:$c}){ workflowState { id name } } }",
  "variables": {"t":"<TEAM_ID>","n":"Blocked","c":"#eb5757"}
}' https://api.linear.app/graphql
```
Repeat with `"n":"Needs Owner","c":"#f2994a"`. Then dump the full state map and record Todo / In Progress / Blocked / Needs Owner / Done IDs:

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ teams { nodes { key states { nodes { id name type } } } } }"}' https://api.linear.app/graphql
```

- [ ] **Step 1.3: Create plain labels** — `app/aigateway`, `app/scoreboard`, `pkg/url4-python-sdk`, `com/url4`, `com/evalstudio`, `com/ensemble`, `com/credentials`, `repo`:

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
  "query": "mutation($n:String!){ issueLabelCreate(input:{name:$n}){ issueLabel { id name } } }",
  "variables": {"n":"app/aigateway"}
}' https://api.linear.app/graphql
```
(`app/desktop`, `app/cli` are NOT created — they wait for name lock, spec §7.)

- [ ] **Step 1.4: Create label GROUPS `type` and `who-acts`** — create the parent, then children with `parentId`:

```bash
# parent (group)
… issueLabelCreate(input:{name:"type"}) …                                   # → <TYPE_GROUP_ID>
# children
… issueLabelCreate(input:{name:"epic",parentId:"<TYPE_GROUP_ID>"}) …        # repeat: feature, bug, task, decision
… issueLabelCreate(input:{name:"who-acts"}) …                               # → <WHO_GROUP_ID>
… issueLabelCreate(input:{name:"design-session",parentId:"<WHO_GROUP_ID>"}) …  # repeat: autonomous, deferred
```
Verify grouping in the Linear UI: children render as `type → epic` and the group enforces one-per-issue. Record all label IDs in `.docs/linear-bootstrap-ids.md`.

---

### Task 2: File the adoption epic; create the branch

- [ ] **Step 2.1: Create the epic**

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
  "query": "mutation($i:IssueCreateInput!){ issueCreate(input:$i){ issue { id identifier url } } }",
  "variables": {"i": {"teamId":"<TEAM_ID>","title":"AI SDLC adoption — Linear work items, repo skills, docs artifacts","labelIds":["<repo>","<type/epic>","<who-acts/autonomous>"],"priority":2,"description":"Spec: docs/spec/2026-07-08-ai-sdlc-adoption-spec.md — implement per docs/plan/2026-07-08-ai-sdlc-adoption.md"}}
}' https://api.linear.app/graphql
```
Expected: identifier `OM-<n>` (call it `OM-E` below; likely `OM-1`). Create sub-issues (same mutation + `"parentId":"<epic id>"`, labels `repo` + `type/task` + `autonomous`) titled: `Cards + CLAUDE.md`, `Skills`, `Agents + scripts + CI`, `Backfill work items`.

- [ ] **Step 2.2: Branch**

```bash
git checkout main && git pull --ff-only && git checkout -b OM-E-ai-sdlc-adoption
```
(Substitute the real number, e.g. `OM-1-ai-sdlc-adoption`.) NOTE: this PR bootstraps the convention it documents — the branch uses the NEW format while CLAUDE.md still says SF-N until Task 5 lands. Deliberate one-time exception; state it in the PR body.

- [ ] **Step 2.3: Epic → In Progress**

```bash
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
  "query": "mutation($id:String!,$s:String!){ issueUpdate(id:$id,input:{stateId:$s}){ issue { identifier state { name } } } }",
  "variables": {"id":"<EPIC_ID>","s":"<In Progress state id>"}
}' https://api.linear.app/graphql
```

---

### Task 3: The two cards

**Files:** Create: `.claude/task-board.local.md`, `.claude/sdlc.local.md`

- [ ] **Step 3.1: Write `.claude/task-board.local.md`** (IDs from `.docs/linear-bootstrap-ids.md`):

```markdown
---
system: linear
workspace: <workspace-slug>
key_source: ~/.config/linear/.env   # LINEAR_API_KEY
endpoint: https://api.linear.app/graphql
team: { key: OM, id: "<uuid>" }
states: { todo: "<id>", in_progress: "<id>", blocked: "<id>", needs_owner: "<id>", done: "<id>" }
labels:
  apps: { aigateway: "<id>", scoreboard: "<id>" }   # app/desktop, app/cli at name lock
  pkgs: { url4-python-sdk: "<id>" }
  coms: { url4: "<id>", evalstudio: "<id>", ensemble: "<id>", credentials: "<id>" }
  repo: "<id>"
  types: { group: "<id>", epic: "<id>", feature: "<id>", bug: "<id>", task: "<id>", decision: "<id>" }
  who_acts: { group: "<id>", design-session: "<id>", autonomous: "<id>", deferred: "<id>" }
priority: { P1: 2, P2: 3, P3: 4 }   # Linear ints: 1 urgent (incidents only), 2 high, 3 medium, 4 low
close_template: |
  Commits: <sha> <message>[, …]
  Gates: <run_gates.py summary / test counts>
  Ledger: docs/work/<file>.md
  Deviations: <none | list>
  Owner-verify: <none | what to check visually>
---

# Ticket rules (bind alongside the task-management skill)

- Labels place the work: `app/*`/`pkg/*` = WHERE (multi-value), `com/*` = product component
  (open set — PRODUCT concepts, never internal modules), `repo` = process work (no app/pkg).
  One `type/*` + one who-acts label per issue (Linear groups enforce it).
- D9: ≥2 app/pkg labels → cross-component epic (`com/X` + all affected labels) with one
  sub-issue per affected app/package. Never a single-app filing, never one mega-ticket.
- New app/package/component ⇒ its label created AND registered here in the same change.
- Every work item gets a mirror `docs/tasks/YYYY-MM-DD-<name>.md` at create; status closed
  in BOTH Linear and the mirror at finish. Linear is the status authority.
- A dev item descending from a product/marketing Asana task carries the Asana URL in its
  description (`asana_url` in the mirror frontmatter). Technical work NEVER goes to Asana.
```

- [ ] **Step 3.2: Write `.claude/sdlc.local.md`**:

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
commit_refs: "Refs: OM-N"
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
git commit -m "feat(OM-E): add task-board + sdlc cards (Linear registry, stack gates)" -m "Refs: OM-E"
```

---

### Task 4: docs tree + artifact placement (+ dogfood mirror/ledger)

**Files:**
- Create: `docs/tasks/`, `docs/work/` (`docs/spec/`, `docs/plan/`, `docs/diagrams/` landed with SF-348)
- Create: `docs/work/TEMPLATE.md` (copy `$SRC/templates/work-ledger/TEMPLATE.md`)
- Modify: `docs/README.md`
- Create: `docs/tasks/2026-07-08-ai-sdlc-adoption.md`, `docs/work/2026-07-08-OM-E-ai-sdlc-adoption.md`

- [ ] **Step 4.1:** `mkdir -p docs/{tasks,work}`; `cp $SRC/templates/work-ledger/TEMPLATE.md docs/work/TEMPLATE.md`. (Diagram already at `docs/diagrams/work-item-topology.{svg,png}`.)
- [ ] **Step 4.2:** Rewrite `docs/README.md`:

```markdown
# docs/ — AI-agentic decision records & SDLC artifacts

- `docs/tasks/`    — work-item mirrors (`YYYY-MM-DD-<name>.md`, frontmatter; Linear is authority)
- `docs/work/`     — work ledgers (`YYYY-MM-DD-<ticket-id>-<desc>.md`, created at start — D8)
- `docs/spec/`     — designs/specs (required before planning)
- `docs/plan/`     — implementation plans (required before implementation)
- `docs/diagrams/` — diagram assets (SVG source + PNG)

Process: see the `task-management` + `sdlc-*` skills and CLAUDE.md "AI SDLC".
Local scratch drafts go to gitignored `.docs/`.
Pre-July-2026 docs live at tag `legacy-monorepo-2026-07-08`.
```

- [ ] **Step 4.3:** Create this work's own mirror + ledger (dogfooding):

`docs/tasks/2026-07-08-ai-sdlc-adoption.md`:
```markdown
---
id: OM-E
linear_url: <epic url>
status: in_progress
type: epic
priority: P1
labels: [repo]
created: 2026-07-08
closed:
---
Adopt the Linear AI SDLC per docs/spec/2026-07-08-ai-sdlc-adoption-spec.md.
```
`docs/work/2026-07-08-OM-E-ai-sdlc-adoption.md`: from TEMPLATE, Intent/Planned/Test plan/Acceptance from this plan; Outcome at close.

- [ ] **Step 4.4: Commit** — `git add docs && git commit -m "feat(OM-E): docs SDLC tree + spec, plan, topology diagram" -m "Refs: OM-E"`

---

### Task 5: CLAUDE.md — AI SDLC section

**Files:** Modify: `CLAUDE.md`

- [ ] **Step 5.1:** DELETE sections `## Git Workflow` (incl. `### Commit Rules`, `### Setup (one-time)`) and `## Planning Tickets`. INSERT:

```markdown
## AI SDLC — MANDATORY

Full process: `task-management` skill (work items) + `sdlc-*` skills (per-stack loop) +
cards `.claude/task-board.local.md` / `.claude/sdlc.local.md`. These rules always hold:

0. **95% confidence gate — TOP RULE.** Never write, assert, or implement anything you are
   not ≥95% confident is both correct AND wanted. Below 95% → STOP and ask first. Applies
   to every rule below and every artifact: code, work items, docs, diagrams.
1. **Work item first.** All work starts as a Linear issue (`OM-N`) carrying its labels —
   `app/*`/`pkg/*` (where it lands) or `repo` (process work); `com/*` when a product
   component is affected; exactly one `type/*` and one who-acts label — plus a mirror
   `docs/tasks/YYYY-MM-DD-<name>.md` (frontmatter: id, linear_url, asana_url?, status,
   type, priority, labels, created, closed). At finish, close status in BOTH.
2. **Work ledger.** Every finished unit has `docs/work/YYYY-MM-DD-<ticket-id>-<desc>.md`
   (created at work start, outcome filled at finish — see the sdlc skills).
3. **Spec before plan, plan before code.** `docs/spec/` artifact required before planning;
   `docs/plan/` artifact required before implementation. Prefer `/superpowers`
   (brainstorming → writing-plans) or similar. Never plan or implement without them.
4. **Diagrams.** Propose the diagramming plugin
   (https://github.com/sergio-bershadsky/ai/tree/main/plugins/diagramming) when it's absent;
   assets live in `docs/diagrams/` (SVG source + PNG).
5. **Branches/commits.** Branch `OM-N-<desc>` (e.g. `OM-12-fix-refresh`). Conventional
   commits; body carries `Refs: OM-N`; never `Co-Authored-By`; never commit to `main`
   (branch protection + `.githooks/pre-commit`; one-time: `git config core.hooksPath .githooks`).
6. **Asana boundary.** Asana is READ-ONLY product/marketing input (`asana-product` skill).
   Technical work items never go to Asana.
7. **Cross-cutting work (D9).** Touching ≥2 apps/packages → epic with `com/<component>` +
   all affected `app/*`/`pkg/*` labels, one sub-issue per affected app/package. Never a
   single-app filing, never one mega-ticket.
```

- [ ] **Step 5.2:** Commit: `git add CLAUDE.md && git commit -m "feat(OM-E): replace Asana git workflow with AI SDLC rules" -m "Refs: OM-E"`

---

### Task 6: `asana-product` skill (read-only transform)

**Files:** Create: `.claude/skills/asana-product/SKILL.md`

- [ ] **Step 6.1:** Author from `~/.claude/skills/asana/SKILL.md`, keeping the API-access block (PAT discovery order, curl pattern, URL parsing) VERBATIM and the read operations (`my tasks`, `workspaces`, `projects`, `tasks <gid>`, `task <gid>`, `search`, `sections`). DELETE: `create`, `update`, `complete`, `move`. Frontmatter description: "Read-only view of product/marketing top-level tasks in Asana. Use to list/read/search product context. NEVER creates or updates anything in Asana." Add:

```markdown
## Hard rules

- READ-ONLY. GET requests only. Any request to create, update, complete, or move an Asana
  task → refuse and point to the `task-management` skill (Linear).
- Asana holds product/marketing top-level tasks defined by product/marketing tooling —
  a SOURCE of context, never a destination for technical work.
- A dev work item descending from an Asana task records the Asana permalink in its Linear
  description and mirror frontmatter (`asana_url`).
```

- [ ] **Step 6.2:** Commit: `git add .claude/skills/asana-product && git commit -m "feat(OM-E): asana-product read-only skill" -m "Refs: OM-E"`

---

### Task 7: `task-management` skill — Linear rewrite

**Files:** Create: `.claude/skills/task-management/SKILL.md`

- [ ] **Step 7.1:** Author using `$SRC/skills/task-management/SKILL.md` as the structural source. Keep verbatim-in-spirit: announce line ("Using the task-management skill — the Linear work-item lifecycle."), card-resolution HARD STOP, single-task-holder rule, lifecycle (PLAN → TICKETS → OWNER REVIEW → PLAN ONE → IMPLEMENT → CLOSE → NEXT), batching, mid-session-discovery (file first, 30s), status-mapping moments, milestones→Linear projects (one per plan doc with 3+ items), close discipline, anti-pattern table. Replace: the affect matrix section → D10 label taxonomy (app/pkg/com plain multi-value; type/who-acts groups; `repo`); ticket-ID/code-registry section → "one team, `OM-N` native; the card's label registry is THE single label source"; D9 section per spec §1; source-board anti-pattern rows → label-discipline rows ("cross-cutting work with a single app label" → D9 STOP; "minting an unregistered label" → register in card first, same commit). Command crib:

````markdown
## Command crib (auth: `export $(grep LINEAR_API_KEY ~/.config/linear/.env | xargs)`; POST {{endpoint}})

# create work item (returns native OM-N)
curl -s -H "Authorization: $LINEAR_API_KEY" -H "Content-Type: application/json" -d '{
 "query":"mutation($i:IssueCreateInput!){issueCreate(input:$i){issue{id identifier url}}}",
 "variables":{"i":{"teamId":"{{team.id}}","title":"…","description":"…",
   "labelIds":["{{labels…}}"],"priority":{{priority.P2}},"parentId":null}}}' {{endpoint}}
# move state (Todo→In Progress at ledger creation; →Blocked/Needs Owner on STOP; →Done at close)
… issueUpdate(id:$id,input:{stateId:"{{states.in_progress}}"}) …
# close comment (MANDATORY before Done — card close_template filled)
… commentCreate(input:{issueId:$id,body:$body}) …
# list open items by label
{"query":"{ issues(filter:{labels:{name:{eq:\"app/aigateway\"}},state:{type:{neq:\"completed\"}}}){nodes{identifier title state{name}}}}"}
````

- [ ] **Step 7.2:** Commit: `git add .claude/skills/task-management && git commit -m "feat(OM-E): task-management skill — Linear work-item lifecycle" -m "Refs: OM-E"`

---

### Task 8: `sdlc-python` + `sdlc-react` skills

**Files:** Create both from `$SRC/skills/<name>/SKILL.md`

- [ ] **Step 8.1:** `cp` both files, then apply IDENTICAL edits inside the SHARED-LOOP regions of BOTH:
  1. Rule 7 runner: `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/run_gates.py <stack>` (+ the "plugin root = two levels up…" parenthetical) → `uv run .claude/scripts/run_gates.py <stack>` (run from repo root).
  2. Rule 1 ledger: `(copy TEMPLATE.md; ledger_dir from the card, default docs/work-ledger/)` → `(copy docs/work/TEMPLATE.md; ledger_dir from the card — this repo: docs/work/, named YYYY-MM-DD-<ticket-id>-<desc>.md per D8)`.
  3. Sibling references: name only the adopted pair (python ↔ react); drop `sdlc-go` mentions from description + LOOP PARITY sentence.
- [ ] **Step 8.2:** Stack sections (outside SHARED-LOOP) stay verbatim.
- [ ] **Step 8.3:** Run parity (Task 10 script) → `LOOP PARITY OK`. Commit: `git add .claude/skills/sdlc-* && git commit -m "feat(OM-E): sdlc-python + sdlc-react rigid-loop skills" -m "Refs: OM-E"`

---

### Task 9: Agents

**Files:** Create both from `$SRC/agents/<name>.md`

- [ ] **Step 9.1:** `sdlc-unit-executor.md` edits: "GitHub issue number" → "Linear identifier (`OM-N`)"; issue read "from the board card's `repo`" → "via the Linear API per the card"; stack resolution "affected paths / `app/*` labels" stays (labels now Linear); STOP table's board moves → Linear state changes (issueUpdate to `blocked`/`needs_owner` + commentCreate); drop `sdlc-go` from the skills list. JSON contract: `"ticket": "<OM-N>"` (string).
- [ ] **Step 9.2:** `ticket-filer.md` edits: entry fields `title, body, labels (from the card registry), priority, type, parent?`; validation against the card's `labels:`/`priority:` maps (unknown value → all-or-nothing reject); procedure → issueCreate crib (labelIds resolved from the card; parentId for sub-issues; NO retitle step); return table `identifier | title | URL | state`.
- [ ] **Step 9.3:** Commit: `git add .claude/agents && git commit -m "feat(OM-E): sdlc-unit-executor + ticket-filer agents (Linear)" -m "Refs: OM-E"`

---

### Task 10: Scripts

**Files:**
- Create: `.claude/scripts/run_gates.py` — `cp $SRC/scripts/run_gates.py` VERBATIM
- Create: `.claude/scripts/check_loop_parity.py`

- [ ] **Step 10.1:** Copy `run_gates.py`; smoke-test:

```bash
uv run .claude/scripts/run_gates.py aigateway    # expected: ALL GATES GREEN (exit 0)
uv run .claude/scripts/run_gates.py scoreboard   # expected: ALL GATES GREEN (exit 0)
```

- [ ] **Step 10.2:** Write `check_loop_parity.py` — the plugin's parity script with:

```python
ROOT = pathlib.Path(__file__).resolve().parent.parent   # .claude/
SKILLS = ["sdlc-python", "sdlc-react"]
# shared_regions() path:
path = ROOT / "skills" / name / "SKILL.md"
```
(rest byte-identical: MARKER regex, drift diff, exit codes 0/1/2)

- [ ] **Step 10.3:** `python3 .claude/scripts/check_loop_parity.py` → `LOOP PARITY OK: sdlc-python, sdlc-react …`. Drift → fix Task 8 edits in BOTH files and re-run.
- [ ] **Step 10.4:** Commit: `git add .claude/scripts && git commit -m "feat(OM-E): run_gates + loop-parity scripts" -m "Refs: OM-E"`

---

### Task 11: CI — `repo-checks.yml`

**Files:** Create: `.github/workflows/repo-checks.yml`

- [ ] **Step 11.1:**

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

- [ ] **Step 11.2:** Commit: `git add .github/workflows/repo-checks.yml && git commit -m "ci(OM-E): loop-parity check on sdlc skill changes" -m "Refs: OM-E"`

---

### Task 12: `working-in-this-repo` skill update

**Files:** Modify: `.claude/skills/working-in-this-repo/SKILL.md`

- [ ] **Step 12.1:** §6: branch `SF-{n}-{description}` + Asana `SF` field → `OM-N-<desc>` ("`N` = the Linear number; labels per `.claude/task-board.local.md`"); commit bullet → body carries `Refs: OM-N`. Routing table: add `Label` column (`app/aigateway`, `app/scoreboard`). §7 pointers: add `task-management`, `sdlc-python`/`sdlc-react`, both cards; `docs/` pointer → "decision records & SDLC artifacts (docs/README.md)".
- [ ] **Step 12.2:** Commit: `git add .claude/skills/working-in-this-repo && git commit -m "docs(OM-E): route working-in-this-repo to Linear SDLC" -m "Refs: OM-E"`

---

### Task 13: Verification sweep

- [ ] **Step 13.1:** `python3 .claude/scripts/check_loop_parity.py` → OK; both `run_gates.py` stacks → ALL GATES GREEN.
- [ ] **Step 13.2:** Stale-reference grep (tracked files):

```bash
git grep -nE 'SF-\{n\}|Asana ticket|asana permalink|docs/plans/|docs/specs/|AAGW-|PUPS-|C-team|C-prefix|1213703035415126' -- . ':!docs/plan' ':!docs/spec' ':!.docs'
```
Expected: zero hits (spec/plan may reference the old flow narratively; they're excluded).
- [ ] **Step 13.3:** End-to-end crib dry-run: create a throwaway issue (labels `repo` + `type/task` + `autonomous`), move Todo→In Progress→Done with a close comment, verify the `type` group rejected a second type label, then `issueDelete` it.

---

### Task 14: Ledger outcome, PR, close discipline

- [ ] **Step 14.1:** Fill Outcome in `docs/work/2026-07-08-OM-E-ai-sdlc-adoption.md`; set mirror + ledger `status: done` / `closed:` date.
- [ ] **Step 14.2:** Push, open PR `feat(OM-E): adopt Linear AI SDLC (skills, cards, agents, scripts, CI)`; body: summary, epic URL, test plan (parity + gates + dry-run), the bootstrap-exception note (Step 2.2), "supersedes SF-N/Asana workflow".
- [ ] **Step 14.3:** After CI green + review + squash-merge: close sub-issues then the epic with the card's `close_template` filled; file backfill items — `repo`: "Lock package names + reserve (pypi/npm/brew)", "GitHub Pages: keep frozen vs disable"; `app/scoreboard`: "Portal vendoring stopgap — revisit with web story"; `pkg/url4-python-sdk` + `com/url4`: "Extract url4 SDK from legacy tag" (epic).

---

## Self-review

- Spec coverage: D1/D2/D10 → Tasks 1–3, 7; D3 → Task 6; D5 → Tasks 8/10; D6/D8 → Task 4; D7/D9 → card rules + CLAUDE.md rules 1/7 (Task 5, incl. rule 0 the 95% gate); §5 → Tasks 9–11; §2.4 → Task 12; §6 phase 5 → Task 14.3. `app/desktop`/`app/cli`/`sdlc-go` deliberately absent (spec §7).
- No placeholders beyond `<uuid>/<id>/OM-E` slots that Tasks 1–2 explicitly produce (inputs, not TBDs).
- Naming consistent: `task-management`, `asana-product`, card paths, `docs/work/TEMPLATE.md`, `Refs: OM-N`, label namespaces `app/ pkg/ com/`.
