---
name: working-in-this-repo
description: Route changes in the ScreamingFace monorepo to the correct app or package, toolchain, CI lane, owner, and release path. Use when starting work, deciding where code belongs, choosing gates, or preparing a branch, commit, or PR.
---

# Working in this repo

Use this as the routing map. Read `CONTRIBUTING.md` for setup, `.claude/sdlc.local.md` for exact
gates, `.github/CODEOWNERS` for reviewers, and the component README for local contracts.

## Current components

| Component | Kind | Purpose | CI |
|---|---|---|---|
| `apps/aigateway` | deployable app | provider auth, encrypted credentials, chat-completion normalization | `aigateway-tests.yml` |
| `apps/scoreboard` | deployable app | public benchmark scoreboard and portal | `scoreboard-tests.yml` |
| `packages/url4` | Python package | URL4 grammar, builders, DAG execution, I/O layers, `Url4Node`, server CLI | `url4-tests.yml` |
| `packages/screamingface` | Python package | Fusion authoring, benchmark loading, grading, aggregation, engine client | `screamingface-tests.yml` |

`packages/screamingface/apps/screamingface-engine` is a temporary development location for the
deployable ScreamingFace URL4 profile. Treat it as application code: it composes `Url4Node`, calls
AI Gateway, and optionally uses SearXNG. Promote it to root `apps/` only after ownership and release
responsibilities are approved.

## Placement rules

- Independently deployed process: root `apps/<name>`.
- Reusable library: `packages/<name>`.
- Never import another app's internals. Share through a package or stable HTTP contract.
- Generic URL4 behavior belongs in `packages/url4`; ScreamingFace model routes, registry metadata,
  connection control plane, and benchmark-facing integration belong to the ScreamingFace engine.
- ScreamingFace benchmark datasets, deterministic graders, and aggregators stay in the SDK process.
- Decision records belong under `docs/spec`, `docs/plan`, `docs/tasks`, and `docs/work`; local scratch
  belongs in gitignored `.docs/`.

## Toolchains and gates

All current components are Python 3.12+ projects using `uv`, ruff, pyright, and pytest. Run commands
from the component root. The authoritative commands are the matching stack in
`.claude/sdlc.local.md` and the path-filtered workflow in `.github/workflows/`.

ScreamingFace changes may affect three coupled surfaces: SDK tests, the temporary engine app tests,
and deterministic notebook/fixture regeneration. Run the complete `screamingface` stack rather
than treating the SDK unit suite as sufficient.

AI Gateway live provider tests are opt-in diagnostics. Never import `litellm-enterprise`; provider
credentials remain in its encrypted ORM store. URL4 must keep its core import graph framework-free;
server dependencies are optional.

## Adding a component

1. Choose `apps/` or `packages/` from the deployment boundary.
2. Give it an isolated toolchain and lockfile.
3. Add a path-filtered CI workflow covering lint, format, types, tests, and required build checks.
4. Register its stack in `.claude/sdlc.local.md`.
5. Add CODEOWNERS, dependency updates, documentation, and an explicit release lane or "not released"
   statement.

## Git and review

- Work item and approved design/plan first, per `task-management` and the relevant SDLC skill.
- Branch `OME-N-<description>`; never commit directly to `main`.
- Conventional commit with `Refs: OME-N` in the body; no `Co-Authored-By` lines.
- Rebase on `origin/main`; do not merge main into the branch.
- Squash-merge after approval and green path-dependent checks.
- PRs spanning components must state the cross-component contract and involve each path owner.

The removed desktop/plugin-server tree remains reference-only at
`legacy-monorepo-2026-07-08`; do not copy it back into the live architecture.
