# Team Development Flow

This is the default collaboration guide for ScreamingFace while the team moves
from solo development to shared PR-based work. Keep it short, update it when a
rule starts causing friction, and treat the repository's existing automation as
the source of truth when it is stricter than this document.

## Branching And Commits

1. Branch names use `SF-{n}-{description}`, where `n` is the Asana `SF` custom
   field value. Example: `SF-142-aigateway-auth`.
2. If a task has no Asana ticket, create one before committing. Use project
   `1213628819033917`, set custom field `1213702745960748` to the next `SF-N`,
   and include the Asana permalink in the commit body.
3. Commit subjects do not have to be strict Conventional Commits. Prefer the
   existing repo style when it fits, such as `feat(SF-138): scaffold aigateway`,
   `fix(SF-137): move listen port`, or `SF-135: extract frontend base`.
4. Default merge strategy is squash merge. It keeps `main` linear and matches the
   recent one-PR-one-main-commit history.
5. During PR development, rebase on `origin/main` instead of merging `main` into
   the branch. Resolve conflicts locally, then push the rebased branch.
6. Force-push is allowed only on your own PR branch after a rebase or cleanup.
   Do not force-push someone else's branch. Never force-push `main`.
7. Direct commits to `main` are forbidden, enforced in layers: branch protection
   on `main` (authoritative), plus a local pre-commit guard — `.githooks/pre-commit`
   (`git config core.hooksPath .githooks`), or the husky hook once you `npm install`
   in `apps/desktop` (husky then owns `core.hooksPath` and carries the same guard).

## PR Lifecycle

1. For Dmitry's first two weeks, Sergey reviews Dmitry's PRs before merge. Dmitry
   can also review Sergey PRs in `apps/aigateway`, scoreboard/portal code, and
   shared docs to build context, but Sergey remains the safety reviewer.
2. After the first two weeks, switch to cross-review by default. Tiny mechanical
   changes may self-merge only if CI is green and the affected owner is not
   surprised.
3. PR authors merge their own PRs after review approval and green required
   checks.
4. Required local checks depend on touched paths. For `apps/server`, run the Ruff
   lint/format checks, non-live unit tests, and the relevant e2e shard when
   behavior changes. For `apps/aigateway`, run the non-live tests, Ruff, Pyright,
   and the LiteLLM Enterprise guard. For `apps/desktop`, run lint and build when
   desktop code is touched.
5. If a required check already fails on untouched `main`, mention the baseline
   failure in the PR and decide whether to fix it first or track it separately.
6. Live tests are opt-in diagnostics, not merge gates. `AIGW_LIVE=1` tests need
   real OAuth credentials; `e2e_live` tests need provider API keys. A skipped live
   test is not a failed PR.
7. Definition of done: code/docs landed, relevant checks reported in the PR,
   Asana moved to the right terminal state, and follow-up tickets filed for
   intentionally deferred work.
8. PR descriptions must include the Asana link, a short summary, test plan, and
   screenshots or recordings for UI changes. The template at
   `.github/pull_request_template.md` prefills these fields.
9. WIP limit is two tickets per developer: one actively coding and one waiting
   for review. Exceptions are allowed for urgent unblockers.

## Branch Protection & Merge Queue

Two-tier CI, so path-filtered checks never deadlock a merge:

1. **On the PR** — the path-filtered `<component>-tests.yml` workflows run for
   fast, relevant feedback. A workflow skipped by its `paths:` filter cannot report
   a required status, so these are advisory, not the hard gate.
2. **In the merge queue** — the same workflows also trigger on `merge_group` (no
   path filter), so the full suite runs against the queued, rebased commit and must
   pass before it lands. This is the authoritative gate, and the queue serializes
   merges so `main` never breaks from stale-base races. Trade-off: every queued
   merge runs all components' suites; add a `dorny/paths-filter` gate later if that
   cost matters.

Admin setup for `main` (one-time; needs repo admin — GitHub → Settings →
Rules/Branches):

- Require a PR before merging; require Code Owner approval.
- Require status checks to pass and branches to be up to date.
- Enable the merge queue for `main`.
- Required checks = the `merge_group`-triggered test jobs (job `test` in each
  `<component>-tests.yml`, matrix-expanded for aigateway: `test (3.12)`,
  `test (3.13)`). Pick the exact contexts from a PR's checks list after the first
  merge-queue run so the names match.

## Cross-Service Collaboration

1. Keep tightly coupled changes in one PR when splitting would create a broken
   intermediate state. Split changes when they can land independently.
2. Bias toward smaller PRs. If a change touches both Sergey-owned and
   Dmitry-owned areas, state the cross-service contract in the PR body.
3. Ownership (routed by `.github/CODEOWNERS`): Sergey owns `apps/server` and
   `apps/desktop`; Dmitry owns `apps/aigateway` and `apps/scoreboard`; Bennett owns
   `web/portal`; Kyle owns `web/public` (marketing site); both leads own `docs`,
   root files, workflows, and release glue.
4. `.github/CODEOWNERS` now auto-routes review requests (added once the team grew
   past ~10 developers). Keep it in sync with item 3.
5. If two PRs touch the same file, the PR opened first has right-of-way. The
   second author rebases, unless the first author agrees to rebase instead.
6. Before changing shared config, root docs, or workflow files, leave a short
   note in the PR body explaining who needs to care.

## Communication

1. Async status is the default. End each workday with a short note covering what
   changed, what is blocked, and what is next.
2. Use GitHub PR comments for code review, Asana comments for ticket status and
   scope decisions, and direct messages for urgent blockers. Link across tools
   when the same decision matters in more than one place.
3. Pairing is on-demand at named milestones: `D-AIGW-002`, `DEMO-015`,
   `D-SCORE-006`, `DEMO-025`, and any blocker that would otherwise cost more
   than the pairing time.
4. Escalate after 30 minutes if blocked on architecture, product intent,
   credentials, or ownership. For local setup/build yak-shaving, debug for up to
   two hours, then ask with the commands and errors already tried.

## Code Quality

1. Existing project tooling is authoritative. Python formatting and linting use
   Ruff; Python type checking uses Pyright; desktop uses the configured
   TypeScript/Electron toolchain.
2. Python targets CI parity with Python 3.12 even if a local venv uses a newer
   interpreter.
3. There is no universal coverage floor. New modules should have tests for core
   behavior; untested new modules should be called out in review with a reason.
   Server CI currently enforces coverage through the server workflow.
4. Use type hints for public Python functions, provider/plugin boundaries, and
   data models. Avoid broad `Any` unless the upstream library genuinely requires
   it.
5. Comments should explain non-obvious intent, tradeoffs, or protocol behavior.
   Do not add comments that restate the code.
6. `apps/aigateway` must never import or install `litellm-enterprise`,
   `litellm.enterprise.*`, or `litellm_enterprise.*`. The guard at
   `apps/aigateway/scripts/check_no_enterprise.py` is part of the test suite.

## Asana Hygiene

1. Both Sergey and Dmitry may create tickets. During Dmitry's first two weeks,
   Dmitry should confirm new non-trivial ticket scope with Sergey before creating
   it, to avoid scope drift.
2. Use the Asana `SF` custom field for branch and commit identity. Do not invent
   an `SF-N` locally.
3. Discovered defects or demo rough edges become follow-up tickets in the same
   Asana batch, labeled or described as `demo-blocker`, `demo-polish`, or
   `post-demo`.
4. Status meanings: `In Progress` means someone is actively working; `In Review`
   means a PR is open and ready for reviewer attention; `Blocked` means the next
   action is external; `Done` means merged or explicitly no-code-complete and the
   acceptance criteria are checked off.
5. If acceptance criteria are intentionally cut, update the ticket before merge
   so the PR and Asana agree on what was actually delivered.

## First-Day Setup

1. Clone the repo and run `git config core.hooksPath .githooks`.
2. Sync Python apps separately: `cd apps/server && uv sync`, then
   `cd ../aigateway && uv sync`.
3. Start the gateway with `cd apps/aigateway && uv run uvicorn aigateway.main:app --port 9105 --reload`, then check `curl -sf http://localhost:9105/healthz`.
4. Run the gateway smoke checks: `uv run pytest -m "not live"`, `uv run ruff check .`, `uv run pyright`, and `uv run python scripts/check_no_enterprise.py`.
5. Start the server with `cd apps/server && uv run sf run --no-ssl` when `mkcert`
   is unavailable.
6. Do not add `scripts/setup-dev.sh` in this pass. The manual setup is short, and
   a script should wait until the aigateway/provider/scoreboard dependency shape
   stabilizes.
