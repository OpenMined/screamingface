---
description: Use for ANY task/ticket work — creating, triaging, planning, implementing, or closing work items — in this repo. All units of work live as Linear issues (OME-N) in the Engineering team under the 😱 ScreamingFace V1 project, per the .claude/task-board.local.md card. Defines the lifecycle (plan → tickets → owner review → per-ticket SDLC → close), the label taxonomy (workstream Epic group, app/pkg landing, who-acts, mandatory actor), STOP labels, close discipline, docs/tasks mirrors, the Linear MCP command crib, and the Linear rich-text dialect. Invoke at session start, before starting any unit of work, and before filing or closing an issue.
user_invocable: true
---

# Task Management — Linear work items

**Announce at start:** "Using the task-management skill — the Linear work-item lifecycle."

## Card resolution — before anything

Read `.claude/task-board.local.md` in the project root. **Missing → HARD STOP:** tell the
user the card is gone and stop — never guess the team, project, states, or label IDs. Every
`{{…}}` placeholder below resolves from that card. Read the card BODY too — its ticket
rules bind alongside this skill.

**Transport: the Linear MCP plugin ONLY** (`mcp__plugin_linear_linear__*` tools; activate
via `/mcp`). **API tokens and raw GraphQL are FORBIDDEN.** Operations the MCP cannot
perform (label/team/state management, issue deletion) are OWNER actions in the Linear UI —
hand them over with precise steps.

The single task holder is the card's team + project. No parallel boards: session-local todo
tools are fine for intra-session step tracking, but any unit of work that outlives the
session MUST be a Linear issue. The work-ledger (`docs/work/`) stays the how/audit record;
the issue is the what/status record — they cross-reference, they don't duplicate. Every
issue additionally gets a repo mirror `docs/tasks/YYYY-MM-DD-<name>.md` (frontmatter: id,
linear_url, asana_url?, status, type, priority, labels, created, closed) — written at
create, closed at finish; **Linear is the status authority**.

## The label taxonomy (locked — D10/D13)

- **Workstream** — the existing `Epic` label group (ONE per issue, Linear-enforced):
  url4 Engine · AI Gateway · Eval Runner & Datasets · Results & Runs · Leaderboard ·
  Auth & Subsidized Compute · Desktop App · Python SDK · Multi-turn Ensembles · SOTA Hunt ·
  Compute Budgeting. Apply whenever the work belongs to one. Workstreams are PRODUCT
  concepts — never mint one for an internal module; additions are coordinated with the
  project lead and registered in the card in the same change.
- **Landing (WHERE)** — plain multi-value labels: `app/aigateway`, `app/scoreboard`,
  `pkg/url4-python-sdk` (more at name lock), or `repo` for repo/process work (no app/pkg).
- **`who-acts` group** (ONE per issue): `design-session` — a direction fork; agents may
  PREPARE, never decide · `autonomous` — agent-runnable end-to-end · `deferred` — recorded,
  gated on a named precondition (state the gate in the body).
- **`actor` group (ONE per issue, MANDATORY — D13):** `agentic` or `human` — who executes
  the work. Set at filing; flip if ownership changes.
- **STOP labels (D12):** existing `blocked ⛔` (hard question pending) and `needs-owner`
  (only a decision/visual check pending). A STOP = apply the label + comment the exact
  question; the issue STAYS In Progress; remove the label when resolved. Never add
  workflow states to the shared team.
- Optional type tagging via existing plain labels `Bug` / `Feature` / `Improvement`.
- **Priority** (Linear ints): P1→2 (High, work next) · P2→3 (Medium, queued) · P3→4 (Low,
  parked); 1 (Urgent) is reserved for incidents. The agent proposes; the owner's setting wins.

**Cross-cutting rule (D9):** work touching **≥2** `app/*`/`pkg/*` landings → file an
**epic** (parent issue) carrying its workstream label + ALL affected landing labels, with
one sub-issue per affected app/package (one SDLC unit each; each sub-issue carries its own
landing label + the same workstream label). Never a single-app filing, never one mega-ticket.

## The lifecycle

```
PLAN (docs/plan artifact) ──▶ TICKETS (one issue per SDLC-unit-sized deliverable;
  multi-unit arcs get a parent epic with sub-issues)
──▶ OWNER TICKET REVIEW (scope/priority/labels; design-session forks resolved or scheduled)
──▶ PLAN ONE TICKET ──▶ IMPLEMENT IT (the stack's sdlc-* loop: ledger → RED → GREEN →
  gates → commit; the ledger names the issue; commit bodies carry `Refs: OME-N`)
──▶ CLOSE (see close discipline) ──▶ NEXT TICKET
```

- **Status mapping:** Todo → **In Progress** when the ticket's ledger is created → **Done**
  when the issue closes. `In Review` while the PR awaits review. STOPs are labels (D12),
  not states. Move status at those moments, not retroactively.
- **Batching:** several INDEPENDENT tickets may run in one batch (one sdlc-unit-executor
  per ticket; sequential when they share a stack). Declare the batch up front — each ticket
  still gets its own ledger, commits, and close comment.
- **Mid-session discoveries:** new work found while implementing → file the ticket first
  (30 seconds), then decide: in-scope for the current unit, or leave it. Never let work
  exist only in a chat transcript.
- **Milestones** belong to the product project (sprints S0–S5, owned by the project lead).
  Product work slots into the current sprint milestone with the lead's agreement;
  repo/process items take no milestone.

## Close discipline

An issue closes ONLY with a comment carrying the card's `close_template` filled: commit
shas + messages, the gates that ran (test counts/baselines), the ledger path(s), deviations,
and anything the owner must verify visually. Wrap long gate output in a `+++ Gates` …
`+++` collapsible. Then set state Done and close the `docs/tasks/` mirror (status + closed
date). Closing without this comment is a process violation.

## Command crib (Linear MCP tools; names resolve via the card)

- **Create:** `save_issue {team: "Engineering", project: "{{project.slug}}", title, description,
  labels: ["repo"|"app/…", "<workstream>", "autonomous"|…, "agentic"|"human"], priority, parentId?}`
  → returns the native `OME-N` identifier + URL. NO id parameter on create.
- **Move state:** `save_issue {id: "OME-N", state: "In Progress" | "In Review" | "Done"}`
- **STOP / un-STOP:** read current labels (`get_issue`), then `save_issue {id, labels: [<union
  ± stop label>]}` + `save_comment {issueId: "OME-N", body: "<exact question>"}`
- **Close comment:** `save_comment {issueId: "OME-N", body: <close_template filled>}`
- **List/find:** `list_issues {project, label?, state?, query?, parentId?}` · `get_issue {id}`
- **New label** (only when the card registers it in the same change): `create_issue_label
  {name, color, description, parent?/isGroup?}`

**MCP quirks (encode these in your calls):**
- `save_issue.labels` **REPLACES the full label set** — always read current labels first
  and resend the union. Relations (`blockedBy`, `relatedTo`, `links`) are append-only.
- Send **raw markdown with literal newlines** — never `\n` escape sequences.
- `assignee` accepts `"me"`, a name, or an email.

## Linear rich text — the markdown dialect for descriptions & comments

- **Headings:** `#`–`####` (H1–H4). Deeper levels don't exist.
- **Text:** `**bold**`, `_italic_`, `~~strike~~`, `` `inline code` ``. Underline has NO
  markdown syntax (editor-only) — don't try.
- **Lists:** `-`/`*`/`+` bullets, `1.` numbered, `- [ ]` checklists (render as interactive
  checkboxes — good for acceptance lists); all nestable.
- **Blockquote:** `>` · **Collapsible section:** `+++ Title` on its own line, content,
  closing `+++` (nestable) — use for long logs/gate output.
- **Code:** fenced ``` blocks with a language tag; ` ```mermaid ` renders a Mermaid diagram.
- **Divider:** `---` · **Tables:** GFM pipe tables (keep simple — no spans).
- **Emoji:** `:name:` · **No HTML** — it is not rendered.
- **Mentions — SIDE-EFFECTS:** `@displayName` notifies + subscribes that user. Issue
  references auto-link aggressively: `@OME-123`, pasted issue URLs, AND bare `OME-123`
  identifiers in plain prose all become issue embeds (verified live) and can create
  "related to" relations. Wrap IDs in backticks when no link/relation is wanted.
- **Embeds:** bare YouTube/Loom/Figma/Google-Docs URLs auto-embed; wrap in `[text](url)`
  to keep a plain link.

## Anti-patterns — STOP immediately

| Thought | Reality |
|---|---|
| "I'll track this in the session todo only." | Outlives the session? It's a Linear issue. File it. |
| "One big issue for the whole plan." | Decompose: epic parent + SDLC-unit sub-issues. |
| "It touches two apps but I'll label just one." | D9 STOP: epic + one sub-issue per affected app/package. |
| "I'll skip the actor label." | D13: `agentic` or `human` is MANDATORY on every item. |
| "Close it, the code's merged." | No close without the commits+gates+ledger comment. |
| "It's a design-session ticket but the answer is obvious." | Prepare a proposal; the owner decides. |
| "I'll mint a label the card doesn't register." | The card is the registry. Register first, same change. |
| "The MCP can't do it — I'll use the API key." | FORBIDDEN. MCP-uncovered ops are owner UI actions. |
| "I'll set labels without reading current ones." | `labels` REPLACES the set — read, union, resend. |
