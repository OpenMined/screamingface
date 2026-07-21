---
description: Use for ANY task/ticket work — creating, triaging, planning, implementing, or closing work items. All units of work are Linear issues in the team + project named in .claude/task-board.local.md. Defines the lifecycle, the label taxonomy (single-select landing groups + actor / who-acts / type), STOP statuses, sprint milestones, close discipline, docs/tasks mirrors, the Linear MCP command crib, and the Linear rich-text dialect. Invoke at session start, before starting any unit of work, and before filing or closing an issue.
user_invocable: true
---

# Task Management — Linear work items

**Announce at start:** "Using the task-management skill — the Linear work-item lifecycle."

> This skill is workspace-agnostic. Every concrete name — team, project, issue-key prefix,
> the label groups and their leaves, milestone/sprint names, status names, the
> `close_template` — resolves from **`.claude/task-board.local.md`** (the "card"). Where this
> doc shows an example set, it is illustrative; the card is authoritative.

## Card resolution — before anything

Read `.claude/task-board.local.md` (at the **repo root** `.claude/`, not beside this skill). **Missing → HARD STOP:** tell the user the card is gone
and stop — never guess team, project, or label IDs. `{{…}}` placeholders resolve from the
card; its body rules bind alongside this skill.

**Transport: the Linear MCP plugin ONLY** (`mcp__plugin_linear_linear__*`; activate via
`/mcp`). **API tokens and raw GraphQL are FORBIDDEN.** Agents act **only on issues** — create
issues; edit an issue's title, applied labels, status, priority, milestone, assignee,
relations, and comments. **Agents do NOT create, rename, delete, reparent, or edit labels** —
all label management (and teams, workflow states, templates, integrations, and issue
deletion) is an **OWNER action in the Linear UI**. When one is needed, hand it over with
precise steps.

Single holder = the card's team + project (`{{team}}` · `{{project}}`). No parallel boards.
Session todos are fine for intra-session tracking; anything that outlives the session is a
Linear issue. The `docs/work/` ledger is the how/audit record; the issue is the what/status
record — they cross-reference, never duplicate. Every issue gets a repo mirror
`docs/tasks/YYYY-MM-DD-<name>.md` (frontmatter: id, linear_url, asana_url?, status, type,
priority, labels, created, closed). **Linear is the status authority.**

## Label taxonomy

Labels are organized as **single-select groups** — one leaf per group per issue, enforced by
Linear — and are **two levels deep**; a sub-component is a slash inside the leaf name
(`desktop/eval-runner`), NOT a real sub-group. The exact groups and leaves live in the card.
**Agents never mint labels.** Need a new leaf? Propose it to the project lead, who creates it
in the UI and registers it in the card in the same change — then apply it to issues.

- **Landing — WHERE the work lands.** One or more top-level groups partition work by landing
  type (application vs package vs cross-cutting vs research, etc.). Pick **exactly one leaf**,
  normally from one group. Leaves carry UI descriptions — trust them.

  > **Example (this workspace's card):** groups `app` / `pkg` / `extra` / `research`, e.g.
  > `app › desktop`, `app › desktop/eval-runner`, `app › aigateway`, `pkg › <lib>`,
  > `extra › <cross-cutting>`, `research › <spike>`. Your card defines the real set.

- **`actor` — `agentic` | `human`.** Who executes. Required on **agent-executed / SDLC**
  items; human-owned roadmap tickets may carry just the landing leaf + assignee (actor = the
  assignee).
- **`who-acts` (one, on SDLC items):** `design-session` (direction fork — agents prepare,
  never decide) · `autonomous` (agent-runnable end-to-end) · `deferred` (gated on a named
  precondition — state it in the body).
- **`type` (one, optional):** `decision` (a locked decision, not code) · `task`
  (mechanical/housekeeping/research — no product-behaviour change). Extend only via the card.
- **STOP is a STATUS, not a label:** move to the **Blocked** state (hard question pending) or
  **Needs Owner** state (only a decision/visual check pending) + comment the exact question;
  move back when resolved.
- **Blockers are RELATIONS, not prose:** if a ticket waits on another, set a **blocked-by**
  relation (not just a "Gate:" line) so the dependency graph is real and ordering surfaces.
- **Priority** (Linear ints): 1 Urgent (launch-blocking) · 2 High · 3 Medium · 4 Low. If the
  workflow has a dedicated "queued next" state, use that for ordering — not priority — and
  keep the two distinct. Agent proposes; owner's setting wins.

**Cross-cutting rule:** an issue carries **at most one** landing leaf. Work spanning ≥2
landings → a parent **epic** + one **sub-issue per landing** (each with its single leaf).
Two leaves from one group are rejected by Linear — that's the signal to split.

## Two ticketing modes

- **Human-filed (roadmap / epic / decision):** use the Linear **issue templates** the card
  lists (typically a default Roadmap template, a Cross-cutting Epic template, and a Decision
  template). The template supplies the body shape and preset labels; the filer adds the
  landing leaf, milestone, priority, assignee.
- **Agent-filed SDLC unit:** filed through the MCP per this skill (deliberately **no UI
  template** — the skill is the template). Carries a landing leaf + `agentic`|`human` + a
  `who-acts` leaf; runs ledger → RED → GREEN → gates → commit (`Refs: <issue-id>`), then the
  close-comment.

## Naming & board conventions

- **Title = imperative summary only.** Do **not** prefix titles with the issue ID — Linear
  shows the ID natively beside every issue. No legacy component prefixes either; the landing
  leaf carries the component. Leaf names are lowercase-kebab.
- **Sprints are milestones** (named + owned by the project lead in the card). Product work
  slots into the active sprint milestone; pure repo/process work takes no milestone.
- Every issue: one landing leaf + priority; product work also gets milestone + assignee.

## Lifecycle & statuses

```
PLAN (docs/plan) ─▶ TICKETS (one per SDLC-unit; multi-landing → epic + sub-issues)
─▶ OWNER REVIEW (scope/priority/labels/milestone) ─▶ IMPLEMENT (sdlc-* loop) ─▶ CLOSE ─▶ NEXT
```
The team's workflow states (exact names per the card) follow the shape: **incoming/backlog →
queued-next → in-progress → in-review → done**, plus the two STOP states (**Blocked**,
**Needs Owner**) and terminal **Canceled** / **Duplicate**.

**If GitHub status automation is enabled** (see the card): opening the PR moves the issue to
*in-review*, merging moves it to *done* (branch names follow `…/<issue-id>-…`;
`Fixes <issue-id>` in the PR body also closes it). In that case you manually set only the
*queued-next* and *in-progress* states (in-progress at ledger creation) and the STOP states —
don't hand-move the in-review/done transitions the PR will drive.

## Close discipline

Even with GitHub auto-done, an issue is only properly closed with the card's `close_template`
filled: commit shas + messages, gates that ran (test counts/baselines), ledger path(s),
deviations, owner-visual-check notes. Long gate output in a `+++ Gates … +++` collapsible.
Then close the `docs/tasks/` mirror. A merge without the close-comment is an incomplete close.

## Command crib (Linear MCP)

- **Create:** `save_issue {team: "{{team}}", project: "{{project.slug}}", title: "<imperative summary>", description, labels: ["<landing leaf>", ("agentic"|"human")?, ("autonomous"|"deferred"|"design-session")?], priority, milestone?, assignee?, parentId?}` → returns the issue ID + URL. NO id on create; NO issue-ID in the title.
- **Move state (only the non-automated ones):** `save_issue {id, state: "<queued-next>"|"<in-progress>"|"<Blocked>"|"<Needs Owner>"}` (use the card's exact state names)
- **STOP:** `save_issue {id, state: "<Blocked>"|"<Needs Owner>"}` + `save_comment {issueId, body: "<exact question>"}`
- **Blocker relation:** `save_issue {id, blockedBy: ["<issue-id>"]}` (append-only; `removeBlockedBy` to clear)
- **Close:** `save_comment {issueId, body: <close_template>}` (a PR merge usually sets done)
- **List/find:** `list_issues {project, label?, state?, query?, parentId?}` · `get_issue {id}` (list truncates descriptions ~500 chars — use `get_issue` for full bodies/relations)
- **New leaf:** OWNER UI action — agents don't create labels. Propose it to the lead; they create it and register it in the card, then you apply it via `save_issue.labels`.

**MCP quirks:**
- `save_issue.labels` **REPLACES the full set** — `get_issue` first, resend the union.
  Relations (`blockedBy`, `relatedTo`, `links`) are append-only.
- Two leaves of one group are rejected/collapsed — the split signal.
- Raw markdown, **literal newlines** — never `\n` escapes. `assignee` = `"me"`/name/email.

## Linear conventions we rely on (owner-configured, not MCP; see the card)

- **Issue templates** for the human-filed modes (Roadmap default · Cross-cutting Epic · Decision).
- **GitHub integration** auto-transitioning status (in-review on PR open, done on merge), where enabled.
- **Single-select label groups** enforcing one leaf per axis (the cross-cutting split signal).
- **Label descriptions** documenting each leaf in the picker — keep them current.

## Linear rich text

Headings `#`–`####`; `**bold**` `_italic_` `~~strike~~` `` `code` `` (no underline);
`-`/`1.`/`- [ ]` lists; `>` quote; **`+++ Title … +++`** collapsible (logs/gates); fenced
code (` ```mermaid ` renders); `---`; GFM tables; `:emoji:`; **no HTML**. **Refs have
side-effects:** `@name` notifies; an `@`-prefixed ID, issue URLs, AND a bare issue ID become
issue embeds + can create relations — wrap IDs in backticks for a plain reference. Bare
YouTube/Loom/Figma/Docs URLs auto-embed; `[text](url)` keeps a link.

## Anti-patterns — STOP

| Thought | Reality |
|---|---|
| "Session todo is enough." | Outlives the session? Linear issue. |
| "One big issue for the plan." | Epic parent + SDLC-unit sub-issues. |
| "Two landings, one leaf." | Group is single-select — epic + one sub-issue per landing. |
| "Prefix the title with the issue ID." | Don't — Linear shows the ID; title is the summary. |
| "Add a `blocked` label." | STOP is a STATUS (Blocked / Needs Owner); waits are blocked-by relations. |
| "I'll hand-set in-review / done." | If GitHub automation is on, the PR does that — set only queued-next / in-progress / STOP. |
| "Close it, code's merged." | Merge ≠ close-comment. File commits+gates+ledger. |
| "design-session, answer's obvious." | Prepare a proposal; owner decides. |
| "I'll create the label I need." | Agents never create labels — propose it; the lead adds it in the UI + card, then you apply it. |
| "MCP can't — use the API key." | FORBIDDEN. Uncovered ops are owner UI actions. |
| "Set labels without reading current." | `labels` REPLACES — read, union, resend. |
