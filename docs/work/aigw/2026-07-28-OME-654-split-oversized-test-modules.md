---
ticket: OME-654
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-654 — Split the oversized test modules this branch authored

## Intent

With the source modules done (OME-602, OME-653), seven test modules authored on this branch remain
above the 450-line limit the plan binds to touched Python files:

| Lines | Module |
|---:|---|
| 605 | `tests/unit/openrouter/test_openrouter_openapi_endpoint_source.py` |
| 600 | `tests/unit/anthropic/test_anthropic_thinking_conflict.py` |
| 556 | `tests/unit/openrouter/test_openrouter_parameter_projection.py` |
| 488 | `tests/unit/anthropic/test_anthropic_parameter_projection.py` |
| 473 | `tests/unit/openrouter/test_openrouter_strict_routing.py` |
| 472 | `tests/unit/test_chat_profile_default_validation.py` |
| 467 | `tests/unit/core/test_chat_parameter_contract.py` |

`tests/unit/test_chat_x_profile.py` (1276) is **out of scope by owner decision**: it was already
1269 lines before this branch existed, so its overage is not this branch's work.

## Verified before starting

- **This is the one change class the branch's strongest gate cannot certify.** Every source split
  was proved by the append-only test check passing *unskipped* — "zero test files changed" was the
  evidence. Moving a test between files makes that gate red by construction, so it cannot serve
  here and must be replaced by a different proof, not simply skipped.
- **Baseline captured before any edit:** 2114 collected tests across the suite, 2082 distinct
  node-ID suffixes (32 same-named tests live in more than one file, which is why the comparison is
  a MULTISET and not a set).
- **Seven of eight oversized test modules were authored by this branch**; the eighth predates it.
  That distinction is what scopes this item.

## Design decisions

**Whole units move verbatim.** A test function, its parametrize decorator, its fixtures and its
local helpers travel together, unedited. Nothing is renamed, re-parametrized, merged or reworded.
An edit inside a moved test would make the node-ID proof below unable to distinguish a
reorganization from a behaviour change, which is the entire reason the proof works.

**Cut along behaviour, not line count.** Each file splits where its own sections already divide —
a module covering both the parser and the wired route splits there, not at its midpoint. A cut that
leaves two arbitrary halves would satisfy the limit and make the suite harder to navigate, which
inverts the point of the limit.

**Sibling modules in the same directory**, matching how the suite is already laid out
(`tests/unit/openrouter/`, `tests/unit/anthropic/`, `tests/unit/core/`). No new package level.

## Planned changes

Seven test modules → sibling test modules alongside each. **No production source file changes** —
that is itself an acceptance criterion, since a source edit hiding inside a test reorganization is
the failure mode this item most needs to exclude.

No schema/model change, so stack rule S1 does not apply.

## Test plan

No new behaviour, so TDD's RED step does not apply. The verification is that the suite is provably
the same suite:

1. **Node-ID multiset identical before and after** for the WHOLE suite, comparing the portion of
   each node ID after the file path — so a test that moves file is unchanged, while a test lost,
   duplicated or renamed in the move shows up as a difference. This is the substitute for the
   append-only gate.
2. Full gate green with append-only skipped **by explicit owner approval** and every other gate
   enforced (ruff, ruff format, pyright, enterprise check, pytest with `--cov-fail-under=80`).
3. Coverage no lower than the pre-split figure.
4. `git diff` touches no file under `src/`.
5. Every resulting test module ≤450 lines.

## Acceptance

- All seven modules, and every file replacing them, at or below 450 lines.
- Identical collected node-ID multiset.
- No production source file changed.
- Full gate green, coverage not reduced.

## Outcome

**All seven modules split; no production source file changed.** Every resulting module is at or
below 450 lines — the largest is 427. Seven modules of 3,661 lines became sixteen files of 4,010;
the difference is module docstrings and the deliberately duplicated harnesses recorded below.

| Original | Was | Now | Sibling(s) created | Lines |
|---|---:|---:|---|---:|
| `openrouter/test_openrouter_openapi_endpoint_source.py` | 605 | 326 | `test_openrouter_openapi_endpoint_route.py` · `_openapi_document.py` | 211 · 127 |
| `anthropic/test_anthropic_thinking_conflict.py` | 600 | 427 | `test_anthropic_thinking_decision.py` | 209 |
| `openrouter/test_openrouter_parameter_projection.py` | 556 | 238 | `test_openrouter_standard_parameter_projection.py` | 403 |
| `anthropic/test_anthropic_parameter_projection.py` | 488 | 256 | `test_anthropic_standard_parameter_projection.py` | 284 |
| `openrouter/test_openrouter_strict_routing.py` | 473 | 381 | `test_openrouter_no_eligible_endpoint.py` | 169 |
| `test_chat_profile_default_validation.py` | 472 | 408 | `test_chat_profile_default_provenance.py` | 82 |
| `core/test_chat_parameter_contract.py` | 467 | 393 | `test_chat_parameter_schema_validation.py` | 96 |

Plus `openrouter/__init__.py` (empty), which the one shared helper module needs.

**Every cut was made by script from line spans, never by retyping**, with an assertion on the first
and last content of each span before anything was written. Two of those assertions fired on a wrong
assumption about a file's last line and stopped the run before it touched disk — the guard doing
exactly its job.

### The proof, since the usual one cannot apply

The append-only gate — "zero test files changed" — certified every SOURCE split on this branch. A
test relocation makes it red by construction, so it was skipped for this item **by explicit owner
approval, scoped to this mechanical relocation only**. Four independent checks replace it:

1. **Collected node-ID multiset identical** across the whole suite — 2114 before, 2114 after, `diff`
   clean — comparing the portion of each node ID *after* the module path, since a split necessarily
   changes the path and nothing else. A test lost, duplicated, renamed, re-parametrized or newly
   skipped in the move would appear here. It is a multiset, not a set: 32 test-name suffixes exist in
   more than one file, and a set comparison would hide a loss.
2. **`ruff format --check` clean on first pass** for thirteen of the fifteen Python files, before any
   formatter ran on them. The moved bodies are byte-for-byte what the formatter already produced;
   mangled indentation or a dropped blank line would have shown up as a wanted reformat.
3. **`git status` touches nothing under `src/`.** Exactly seven modified files and eight new ones,
   all under `tests/`.
4. **Full gate green** and coverage measured at **92%** (7782 statements, 608 missed), 2074 passed /
   40 skipped. Coverage cannot have moved: it is a function of the source measured and the tests
   executed, and both are provably unchanged.

**Gates:** `run_gates.py aigateway --skip-append-only` → ruff check ✓, ruff format --check ✓,
pyright ✓, `check_no_enterprise.py` ✓, pytest `--cov-fail-under=80` ✓ — **ALL GATES GREEN**.
Enabled-OpenRouter conformance re-run after the split: 11 passed.

**Scope recheck against the merge base.** Thirteen Python files in the app remain above 450 lines;
twelve are byte-identical to the merge base and were authored by earlier merged PRs — including
`openrouter/test_openrouter_error_policy.py` (475) and `openrouter/test_api_key_validation.py` (474),
which sit in a directory this branch worked in heavily and were checked individually rather than
assumed. The only over-450 file this branch touched is `test_chat_x_profile.py`, out of scope by
owner decision. The census of seven was correct.

### Deviations

- **Harnesses were DUPLICATED verbatim, not shared — and this is a correctness requirement, not a
  shortcut.** `_api_key_validation_ok` in the two OpenRouter modules is an **autouse** fixture, and an
  autouse fixture applies only to the module that defines it. Importing it would be a different thing
  from declaring it, and moving it to a `conftest.py` would silently widen it to every sibling module.
  Copied: the full harness in `test_openrouter_standard_parameter_projection`; `_MODEL` / `_UPSTREAM` /
  `_MESSAGES` / `_dispatch_body` / `_rules` in `test_anthropic_standard_parameter_projection`; both
  fixtures plus `_create_connection` / `_post_chat` in `test_openrouter_no_eligible_endpoint`; `_TOOLS`
  in `test_anthropic_thinking_decision`. All are stateless or monkeypatch-based and function-scoped,
  so two definitions behave exactly as one did. Per-file `_TOOLS` is already the house norm here.
- **One exception to that rule: `_openapi_document.py` is shared.** Its payload is a slice of the REAL
  OpenRouter document measured 2026-07-28, and its entire value is that it was not invented. Two
  copies would quietly become two different documents, and the test that catches a wrong component
  name would start passing against a fixture nobody checked. Verified safe before sharing: no test
  mutates `_OPENAPI` or `_CATALOG`, and `_RoutingClient` holds no class-level mutable attributes
  (`seen` is per-instance) — so lifetime and isolation are what they were when one module owned them.
- **`_raising_acompletion` and `_returning_acompletion` MOVED rather than being copied**, because
  nothing in the strict-routing policy module uses them. Copying would have left two dead helpers.
- **Imports adjusted only as the move required:** dropped `litellm` (anthropic standard — every
  remaining mention there is a comment or the `litellm_params=` keyword), `httpx` + `NotFoundError`
  (strict-routing origin), `_apply_defaults` (default-validation origin), `ParameterValidationError`
  (contract origin), and the eight contract-only imports from the thinking origin. Each was confirmed
  unused in its half by count before removal, and `ruff` independently agreed.
- **`_MESSAGES` was copied without its three-line rationale comment**, which explains a `list[Any]`
  annotation needed by `_wire_json` — a helper that did not move. The annotation itself is verbatim.
- **Two trailing blank lines were removed by `ruff format`** at cut points, inspected via
  `--diff` before being applied. No other formatting change was accepted.
- **No RED step, deliberately.** There is no new behaviour; the inverse — the same suite, provably the
  same tests, green — is the stronger claim.
- **`tests/unit/test_chat_x_profile.py` (1276) was left alone** by owner decision: it was 1269 lines
  before this branch existed, so splitting it is surgery unrelated to OME-479.
- **No schema/model change**, so stack rule S1 does not apply.
