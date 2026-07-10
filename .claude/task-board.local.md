---
system: linear
workspace: openmined
transport: "Linear MCP plugin (plugin:linear) — the ONLY transport; PRECONDITION: activate via /mcp. API tokens/GraphQL FORBIDDEN; MCP-uncovered ops (label/team/state management) are owner actions in the Linear UI"
team: { key: OME, name: Engineering, id: "5f4d721f-4452-4ed1-990a-7cdbcd923508" }
project: { name: "😱 ScreamingFace V1", slug: screamingface-v1-27666092fc7f, id: "7cbe5759-cc07-476d-b81e-da05b6b2d4d7" }
states:
  todo: "88de5fec-8ce3-4172-b462-6c418837accf"
  in_progress: "03621515-86a4-4669-aad7-5467a23505f1"
  in_review: "62b4c1a3-752f-456b-bdf6-7ce484959e5d"
  done: "699b96ac-cd89-42db-a717-4f8b291a7388"
  triage: "a6fc6a19-f6fd-4fda-baf6-2d26cc54adae"
labels:
  epic_group:  # existing workstream axis (Linear group "Epic", one per issue) — adopted as-is (D10)
    "url4 Engine": "4cf80371-0eab-48e3-b396-efbf5b4837a7"
    "AI Gateway": "554a9f5f-0535-4165-be15-60c5385f2c2a"
    "Eval Runner & Datasets": "f4d5724b-34ab-47f0-b7bd-cfa3d420c0fb"
    "Results & Runs": "0aff5dce-0a3e-4797-96e8-60b2098ef657"
    "Leaderboard": "7f2af383-b322-45a6-8d37-cd45a8dcd3e5"
    "Auth & Subsidized Compute": "016ca5be-1d4b-475f-b19d-cd3a6d43db6b"
    "Desktop App": "481804a4-453c-4ceb-8a47-6e3745ee440a"
    "Python SDK": "dced9623-7411-41a3-83f3-3ce817b02cf6"
    "Multi-turn Ensembles": "2e1ab59e-2806-4d99-96d0-074bbfd1adb4"
    "SOTA Hunt": "2f3ff3a5-8147-4aad-856c-84dea081fde3"
    "Compute Budgeting": "81708f79-1d29-4103-b61c-8d23a221ffd7"
  landing:  # WHERE the work lands — multi-value plain labels; app/desktop + app/cli at name lock
    "app/aigateway": "70c87650-e737-49e5-8e5e-09d4c9649fab"
    "app/scoreboard": "035ce6ac-dc2b-4560-86ae-fe93807702b0"
    "pkg/url4-python-sdk": "65e0b370-12c8-45e4-9b9d-0fb5fe72bac8"
    "repo": "89353e43-30b4-4e4b-b0a6-d781f9dcfebc"
  stop:  # D12: STOPs are labels + comment (issue stays In Progress), never new states
    "blocked ⛔": "f97992bc-7374-44fb-abca-2faf289f915f"
    "needs-owner": "b2542eee-1aa6-4af3-8b9d-41baa3618fd8"
  who_acts:  # Linear group — one per issue
    group: "a5829dd1-ee74-4212-9641-1b3c198778ac"
    "design-session": "b23148b7-7779-415d-b1c8-5480fa967067"
    "autonomous": "6c277f7f-e4b3-41c6-b1ba-406781bb84ed"
    "deferred": "24c84d24-251d-42d0-ba0f-d0c174a68809"
  actor:  # Linear group — MANDATORY, one per issue (D13)
    group: "4060acd7-9bee-41dc-9e45-da9b432d6f89"
    "agentic": "836136d4-994f-457a-9e5e-7f14cf15b4f1"
    "human": "6bb84ba1-b63e-43d6-a061-b80db8565ecf"
  type_ish:  # existing plain labels, optional tagging
    "Bug": "834f8e74-7b87-4af7-a8a7-2462451c4b42"
    "Feature": "67b0111f-30e1-4aa1-bc7f-8ca8f3880890"
    "Improvement": "923adfec-c4eb-4108-ad1b-aefb3e3bd72a"
priority: { P1: 2, P2: 3, P3: 4 }  # Linear ints; 1 (Urgent) reserved for incidents
close_template: |
  Commits: <sha> <message>[, …]
  Gates: <run_gates.py summary / test counts>
  Ledger: docs/work/<file>.md
  Deviations: <none | list>
  Owner-verify: <none | what to check visually>
---

# Ticket rules (bind alongside the task-management skill)

- Every work item: team Engineering + project 😱 ScreamingFace V1 (D11) + a landing label
  (`app/*`/`pkg/*`, or `repo` for process work) + one `who-acts` label + one `actor` label
  (agentic|human — D13, MANDATORY). Add the workstream (`Epic` group) label whenever the
  work belongs to one; workstream additions are coordinated with the project lead.
- D9: ≥2 `app/*`/`pkg/*` labels → cross-cutting: epic carrying the workstream label + all
  affected landing labels, with one sub-issue per affected app/package (one SDLC unit
  each). Never a single-app filing, never one mega-ticket.
- D12 STOPs: apply `blocked ⛔` or `needs-owner` + a comment stating the exact question;
  the issue stays In Progress; remove the label when resolved. Never add workflow states
  to the shared team.
- MCP quirks: `save_issue.labels` REPLACES the whole set — read current labels and resend
  the union. Relations (blockedBy/relatedTo) are append-only. Send raw markdown with real
  newlines. Bare `OME-N` identifiers auto-link and may create relations — wrap in
  backticks when no link is wanted.
- New app/package/workstream ⇒ its label created AND registered here in the same change.
- Every work item gets a mirror `docs/tasks/YYYY-MM-DD-<name>.md` at create; status closed
  in BOTH Linear and the mirror at finish. Linear is the status authority.
- A dev item descending from a product/marketing Asana task carries the Asana URL in its
  description (`asana_url` in the mirror frontmatter). Technical work NEVER goes to Asana
  (`asana-product` skill is read-only).
