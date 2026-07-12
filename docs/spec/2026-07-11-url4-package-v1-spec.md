---
title: url4 SDK v1 — package & commit into packages/url4
status: approved-design, pending-implementation
created: 2026-07-11
author: Claude (Opus 4.8) + ionesio
ticket: OME-397
related:
  - https://linear.app/openmined/issue/OME-397/package-and-commit-url4-sdk-v1-under-sdlc
  - docs/plan/2026-07-11-url4-package-v1.md
  - docs/tasks/2026-07-08-url4-sdk-extraction.md (OME-367 — earlier deferred extraction intent)
  - .claude/skills/url4-engine/SKILL.md (url4 execution & telemetry doctrine)
---

## Problem / intent

The **url4 SDK v1** already exists as source (grammar, parser, AST, DAG interpreter, I/O
ports, tests, examples) but has not entered the monorepo's history under the AI SDLC
process. It lives as an in-flight working tree on a divergent local `main` (base + uncommitted
modifications + new source/test files) rather than as a reviewed, gate-passing commit on a
clean branch off up-to-date `main`.

This unit **packages and commits** that current state into `packages/url4` as one fresh,
SDLC-tracked deliverable. It is explicitly **not** a re-development: the code is taken as-is;
the work is the packaging discipline (spec → plan → ledger → gates → conventional commit),
the correct tracked file set, and clean entry into history without altering `main`.

## What url4 is (context, not new work)

url4 is a standalone, framework-free core library for the **url4 expression protocol**. An
expression reads `(sources)!intent` — "given this data, do this" — and composes recursively,
with `$name` / `$N` references (and their `.field` / `[N]` paths) resolved through a lexical
scope. Key properties:

- **Compilation to a DAG.** An expression compiles into an executable graph of typed nodes
  (`url4.dag`); each node owns its logic behind the `DagNode` protocol, independent nodes run
  in parallel, and nested fragments parse lazily inside the node that owns them.
- **Inverted I/O.** All I/O sits behind the `IOLayer` port (`StaticIOLayer`, `HttpIOLayer`),
  so the core is deterministic and testable without network or framework coupling.
- **Iteration & broadcast.** `src*(body)!intent` resolves to a JSON array of per-row results;
  `!*` broadcast to a JSON array of per-source result objects.
- **Public surface.** `compile_expression`, `run`, the node/AST types, error hierarchy
  (`Url4Error` and friends), and sub-request encode/decode helpers — see `url4.__all__`.

Package metadata: distribution name `url4`, version `0.2.0`, `requires-python >=3.12`, one
runtime dependency (`httpx`), hatchling build backend, ruff + pyright + pytest tooling.

## Scope

- **In:** land `packages/url4/` — `src/url4/**`, `tests/**` (including the new `tests/spec/`
  suite and `tests/test_scan.py`), `examples/**`, `pyproject.toml`, `pyrightconfig.json`,
  `uv.lock`. Author this spec, the plan, the work ledger, and the task mirror.
- **Out:** any change to url4's behavior or API; the new-component coordination contract
  (CI workflow, CODEOWNERS entry, dependabot ecosystem, release lane, `sdlc.local.md` stack
  entry) — those are follow-ups, not part of this packaging unit; assigning/altering the
  product workstream label (owner-coordinated).

## Constraints & invariants

- **No re-development.** Source is committed as-is from the current working tree.
- **Clean tracked set.** Track code + packaging metadata only; never track `.venv`,
  `.ruff_cache`, `.pytest_cache`, `.coverage`, `__pycache__`, `.claude`.
- **History safety.** New branch off up-to-date `main`; `main` history is never rewritten;
  nothing is pushed.
- **Self-contained.** The package carries its own lockfile + toolchain config and depends on
  no other app's internals (matches the `packages/` contract in `working-in-this-repo`).

## Acceptance

- `packages/url4` tracked set = the prior 32-file base **plus** `src/url4/_annotations.py`,
  `tests/spec/` (11 files), and `tests/test_scan.py` — 44 files; no junk tracked.
- url4's own gates pass: `ruff check`, `ruff format --check`, `pyright`, `pytest`.
- Spec + plan + ledger + task mirror committed with the code; conventional commit carrying
  `Refs: OME-397`; nothing pushed.
