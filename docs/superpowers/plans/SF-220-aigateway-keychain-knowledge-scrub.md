# SF-220 — Erase aigateway keychain knowledge from non-code sources

**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215129909003558
**Branch:** `SF-220-aigateway-keychain-knowledge-scrub`
**Depends on:** SF-219 (code rip) — land first, otherwise supersede banners point at unmerged work.
**Confidence:** ~97%

## Goal

After SF-219 deletes the aigateway keychain code, scrub every **aigateway-related** "keychain" reference from non-code knowledge sources (Asana, CLAUDE.md, skills, superpowers plans/specs, auto-memory) so future planning sessions don't re-introduce the pattern. Keychain references tied to `apps/desktop` (Electron `safeStorage`) and `apps/server` (Claude Code OAuth read) are **intentional and must be left alone**.

## Inventory (verified by `grep -rn -i keychain`)

### Superpowers plans/specs — aigateway-related (scrub)

- `docs/superpowers/plans/2026-04-30-aigateway-profile-auth-implementation.md`
- `docs/superpowers/plans/2026-05-07-aigw-backend-oauth-authenticate-button.md`
- `docs/superpowers/specs/2026-04-30-aigateway-profile-auth-design.md`
- `docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md`

### Superpowers plans — NOT aigateway (leave alone)

- `docs/superpowers/plans/SF-198-remove-anthropic-api-key.md` — Claude Code OAuth keychain probe in `apps/server` tests. Intentional.
- `docs/superpowers/plans/SF-199-e2e-oauth-passthrough.md` — same.
- `docs/superpowers/plans/SF-219-aigateway-ormstore.md` — this is the rip plan; keychain mentions are in "what to remove" context. Leave.

### CLAUDE.md

- `/Users/sergey/work/openmind/screamingface/CLAUDE.md` — does **not** currently mention keychain. Add a one-line storage-policy note under Architecture Principles: *"aigateway persistence uses ORMStore (SQLite local, Postgres prod); no OS keychain. Keychain use in `apps/desktop` and `apps/server` is intentional and unrelated."*
- `apps/aigateway/CLAUDE.md` — created by SF-219. Verify the guardrail block is present and matches the SF-219 plan wording.

### Skills

- `/Users/sergey/.claude/skills/`, `/Users/sergey/.claude/CLAUDE.md`: zero hits. No-op now; revisit if a future drift introduces aigateway+keychain language.

### Auto-memory (`/Users/sergey/.claude/projects/-Users-sergey-work-openmind-screamingface/memory/`)

- `project_active_workstream_aigateway.md` — line "SF-139 anthropic provider plugin (OAuth keychain + auth strategy + model registration)". Replace "OAuth keychain" with "OAuth credential store (ORMStore)".
- New file `project_aigateway_no_keychain.md` — guardrail memory pointing at SF-219/SF-220. Add to `MEMORY.md` index.
- Other memory files mentioning aigateway (`project_ownership_map.md`, `project_multibackend_roadmap.md`) do not mention keychain — no change.

### Asana tickets

Audit results (verified via `tasks/search?text=keychain`):

| Ticket | Action | Reason |
|---|---|---|
| SF-202 — "Move aigateway plugin config into Plugin class via pydantic-settings" | **Rescope or close.** | Body describes `keychain_service`/`keychain_account` config fields that no longer exist after SF-219. Either rewrite to `credential_service`/`credential_account` or mark obsolete. |
| SF-186 — "[D-AIGW-008] aigateway Helm chart" | **Edit description.** | Two lines reference "CLI keychains on the host" in dev-deployment notes. Replace with "OAuth credential store seeded via aigateway's auth routes". |
| SF-170 — "[DEMO-029] SF desktop aigateway login flow + JWT session storage" | **Leave alone.** | Describes Electron `safeStorage` in `apps/desktop`. Intentional. |
| SF-169 — "[DEMO-027] SF backend plugins consume aigateway OAuth Connections" | **Leave alone.** | References reading `~/.claude/credentials`, `~/.codex/auth.json`, `~/.gemini/oauth_creds.json` in `apps/server` backend plugins. Intentional CLI-keychain pattern, not aigateway. |
| Completed tickets (SF-77, SF-78, SF-83, SF-132, SF-137, SF-139, SF-140, SF-149, SF-163, SF-172, SF-174, SF-196, SF-198, SF-199) | **Leave alone.** | History; either intentional (server-side) or already closed work that SF-219 supersedes. Don't rewrite closed tickets. |

## Build sequence

1. **Verify SF-219 has merged.** If not, stop — the supersede banners refer to merged work.
2. **Banner the four aigateway plans/specs.** Prepend a single block at the top of each:
   ```markdown
   > **Superseded by SF-219 / SF-220.** This document was written when
   > aigateway used the OS keychain for credential storage. As of SF-219,
   > aigateway uses an ORM-backed credential store (SQLite local, Postgres
   > prod). Keychain references below are historical only.
   ```
3. **Edit `/Users/sergey/work/openmind/screamingface/CLAUDE.md`.** Add the one-line storage policy under Architecture Principles.
4. **Update auto-memory.**
   - Edit `project_active_workstream_aigateway.md` — rewrite the SF-139 bullet.
   - Create `project_aigateway_no_keychain.md` with frontmatter (type: feedback) and content covering the rule + why + how-to-apply.
   - Add a one-line entry to `MEMORY.md` index.
5. **Edit Asana SF-202.** Either: (a) rewrite the description to use `credential_service`/`credential_account` and re-point at the new pydantic-settings target; or (b) mark complete-as-obsolete with a comment referencing SF-219. Pick (a) if the pydantic-settings refactor still has value post-SF-219.
6. **Edit Asana SF-186.** Replace the two CLI-keychain lines in the description's deployment-notes section.
7. **Verify** `grep -rn -i keychain docs/superpowers /Users/sergey/work/openmind/screamingface/CLAUDE.md /Users/sergey/work/openmind/screamingface/apps/aigateway` returns only:
   - Lines inside `apps/aigateway/` test docs or migration comments that explicitly describe the post-SF-219 state (zero expected).
   - SF-219 / SF-220 plan files themselves (intentional).
   - `apps/server/` and `apps/desktop/` references (intentional, untouched).
   - SF-198 / SF-199 plans (intentional, untouched).

## Risks

- **Rewriting closed history.** Don't edit completed Asana tickets or merged plans/specs beyond the supersede banner — that destroys the audit trail. The banner pattern preserves history.
- **Drift between rule and reality.** If the SF-219 guardrail in `apps/aigateway/CLAUDE.md` doesn't actually exist post-merge, this ticket can't ship. Step 1's verification is load-bearing.
- **Asana SF-202 rescope decision.** Whether to rewrite or close is a product call. Default to rewrite (preserve the pydantic-settings goal); ask Trask if unclear.

## Verification (must pass before merge)

- `grep -rn -i keychain apps/aigateway docs/superpowers /Users/sergey/work/openmind/screamingface/CLAUDE.md` — every remaining hit is either an SF-219/SF-220 plan, a banner, or a comment explicitly describing pre-SF-219 history.
- New memory file exists and is linked from `MEMORY.md`.
- Asana SF-202 and SF-186 descriptions edited; permalinks captured in commit message.
- Apps/desktop and apps/server keychain references unchanged: `git diff main -- apps/desktop apps/server` shows zero keychain-related edits in this branch.
