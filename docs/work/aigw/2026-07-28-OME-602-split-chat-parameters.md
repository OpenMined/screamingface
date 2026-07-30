---
ticket: OME-602
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-602 — Split the contract vocabulary module below the file-size guideline

## Intent

`core/chat_parameters.py` is **643 lines** against the ≤450 guideline the plan binds to touched
Python files. It crossed at 463, was accepted with a documented deviation twice, and has grown
since — 498 when this item was filed, 584 at the readiness review, 643 after the auth-applicability
work. The overage is compounding, which is the point at which it gets fixed rather than re-accepted.

This is a **behavior-preserving** split. It carries no functional change and is committed
separately from every functional commit in this branch.

## Verified before starting

- **The seam is real and already marked.** Line 431 carries `# --- pure rule algebra ---`. Above
  it: published enums, reason vocabulary, exceptions, and seven Pydantic value types. Below it:
  six pure functions. The algebra depends on the types; nothing depends the other way.
- **No module reaches across for a private name.** `_REQUEST_PATH_RE`, `_WRAPPER_PREFIX`,
  `_TYPE_PREDICATES` and the three `_DISABLED_*` reason constants are referenced nowhere outside
  this module. `core/parameter_projection.py` defines its own `_WRAPPER_PREFIX` from `WRAPPER_KEY`
  rather than importing this one.
- **The public surface is 26 names**, all re-exported unchanged, so no import site anywhere in
  `src/` or `tests/` needs to move.

## Design decisions

**A package with a re-exporting `__init__`, not two sibling modules.** `aigateway.core.chat_parameters`
is imported by every provider plugin and much of core. Keeping that exact dotted path as the public
entry point is what makes the change mechanical: every existing `from aigateway.core.chat_parameters
import X` keeps working, so the test suite is the proof of behavior preservation precisely because
none of it had to change.

**Private submodule names (`_types`, `_algebra`).** The leading underscore says the layout is an
implementation detail — callers import from the package, never from a half. If a future split moves
a name between halves, no caller breaks.

**All three `_DISABLED_*` reason strings stay together in `_types`.** Two of them are used only by
the algebra, so usage alone would scatter them. They are one published wire vocabulary sharing one
explanatory comment block, and splitting the group would lose the comparison between them;
`_algebra` imports the two it needs.

## Planned changes

- `src/aigateway/core/chat_parameters.py` → deleted, replaced by:
  - `src/aigateway/core/chat_parameters/__init__.py` — module docstring and the re-exported surface.
  - `src/aigateway/core/chat_parameters/_types.py` — vocabulary, exceptions, value types.
  - `src/aigateway/core/chat_parameters/_algebra.py` — the six pure derivations.

No test changes. No schema/model change, so stack rule S1 does not apply.

## Test plan

There is no new behavior to drive with a new test, so TDD's RED step does not apply — the
verification is the inverse: **the entire existing suite must pass untouched**. A split that needed
a test edit would not have been behavior-preserving. Specifically:

1. Full aigateway suite green with zero test files modified (the append-only gate, run without a
   skip, is the mechanical proof).
2. `ruff check`, `ruff format --check` and `pyright` green — pyright is what catches a name that
   failed to survive the move, since every caller still imports from the package path.
3. Enabled-OpenRouter conformance green.
4. Every resulting file at or below 450 lines.

## Acceptance

- `aigateway.core.chat_parameters` exposes exactly the same 26 public names as before.
- No import site in `src/` or `tests/` changed.
- Every file in the new package is ≤450 lines.
- Full gate green; no prior test touched.

## Outcome

- **Actual files (as planned, exactly three):**
  - `core/chat_parameters/__init__.py` — **85 lines**. Carries the original module docstring plus
    an implementation note naming the layout an implementation detail, then re-exports the 26 names with
    `__all__`.
  - `core/chat_parameters/_types.py` — **424 lines**. Vocabulary, exceptions, seven value types,
    `stream_transport_capability`.
  - `core/chat_parameters/_algebra.py` — **244 lines**. The six pure derivations.
  - `core/chat_parameters.py` — deleted. Git recorded it as a **rename** to `_types.py`, so the
    review diff is 243 changed lines rather than 643 deleted + 643 added.
- **Commit:** `bff0b3de` — `refactor(aigateway): split the contract vocabulary module into a
  package` (`Refs: OME-602`).
- **Gates:** `run_gates.py aigateway` → ALL GATES GREEN, run **without** `--skip-append-only`
  (append-only ✓, ruff check ✓, ruff format --check ✓, pyright ✓, `check_no_enterprise.py` ✓,
  pytest with `--cov-fail-under=80` ✓).
- **Behaviour preservation, proved three ways rather than asserted:**
  1. **Zero test files touched** — the append-only gate passing unskipped is the machine proof.
  2. **pyright green** — every import site in `src/` and `tests/` still resolves against the
     package path, which is what would break first if a name failed to survive the move.
  3. **Surface equality diffed against the previous revision**, not eyeballed: the public names of
     the `HEAD` module were extracted by AST and compared to `dir()` of the imported package —
     `missing: NONE`, `newly exposed: NONE`, 26 vs 26, and `set(__all__) == surface`.
- **Every file ≤450**: 85 / 424 / 244.

### Deviations

- **`__all__` turned out to be load-bearing, not decoration.** Without it the package would also
  re-export whatever the halves imported — `AuthMode`, the pydantic names, `re` — quietly widening
  the public surface while every test still passed. The surface-equality check is what caught that
  this needed to be explicit; `newly exposed: NONE` is the assertion that matters most here.
- **Git recorded a rename rather than a delete+add.** Making `_types.py` the file that inherits the
  original's identity (rather than, say, giving `__init__.py` the bulk) keeps the rename diff focused
  on code that actually left the file. That was not the reason for the layout, but it is why the
  layout is worth keeping if a future split moves more code.
- **No RED step, deliberately.** There is no new behaviour to drive a failing test, and inventing
  one would have tested the split's own scaffolding rather than the system. The inverse check —
  the whole suite green with nothing edited — is the stronger claim, and it is machine-enforced.
- **No schema/model change**, so stack rule S1 does not apply.
