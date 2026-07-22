---
ticket: OME-536
stack: url4
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-536 — url4 package-wide quality cleanup

## Intent

A four-angle quality review (reuse, simplification, efficiency, altitude) of the
whole `packages/url4` package surfaced ~18 behaviour-preserving cleanups. This
unit applies them: remove derivable/dead state that must otherwise be maintained
by hand, guard three measured hot paths, and give the duplicated top-level
scanners a single home. No semantic change — the 1073 existing tests are the
contract, and all must stay green without modification.

## Planned changes

Tier A — contained:

- `src/url4/core/ensemble.py` — brace guard before `_json_blob_spans`
- `src/url4/peer/client.py`, `src/url4/peer/server.py` — `render(..., check=False)` on request paths
- `src/url4/__init__.py` — lazy `HttpIOLayer` via PEP 562 `__getattr__`
- `src/url4/dag/nodes.py` — hoist the row-invariant expr in `MapNode`; drop `_Gathered.resolved`,
  `MapNode.label`, the `sem is None` fork
- `src/url4/dag/compiler.py` — drop `_Intent.is_text` and `_ast_label`
- `src/url4/io/layer.py` — drop unused `FetchRequest.timeout`
- `src/url4/core/render.py` — drop two tautological `intent is not None` re-checks
- `src/url4/core/subrequest.py` — reuse `_annotations.EXPRESSION_BEARING_KEYS`
- `src/url4/core/grammar.py` — compute `_first_colon` once in `_parse_head`
- `src/url4/cli/_serve.py` — hoist the params JSON out of the `re.sub` callback

Tier B — dedup:

- `src/url4/core/_scan.py` — home for `strip_one_paren_layer`, `find_unquoted`, and the single
  depth-0 `*(` iteration primitive; `parser.py` / `grammar.py` become thin adapters
- `src/url4/dag/node.py` — `children()` on the `DagNode` protocol; `GuardNode` overrides;
  `executor._dag_children` and `Graph.walk` drop the `isinstance` special-case

## Test plan

Existing suite is the contract (no test edits expected). Gates: `pytest` (1073 baseline),
`ruff check` (strict C901 / PLR0911 / PLR0912 / PLR0915 / PLR1702), `pyright` (0 errors).
Import-cost claim verified with `python -X importtime`; `tests/unit/test_import_isolation.py`
guards the lazy-transport property.

## Acceptance

- All three gates green, test count unchanged at 1073, no test modified to accommodate a change.
- `import url4` no longer pulls httpx.
- No remaining duplicate of the paren/unquoted/iteration scanners.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** 13 modules under `src/url4/` as planned, plus one stale comment in
  `tests/unit/test_dag.py` (it named the removed `is_text` flag). No test logic changed.
- **Commits:** <sha — chore(url4): package-wide quality cleanup>
- **Gates:** ruff clean · ruff format clean · pyright 0 errors · pytest 1073 passed,
  coverage 97.45% (>= 95). Test count unchanged from the pre-change baseline.
- **Measured effects:**
  - `import url4` 95ms -> 49ms cumulative; httpx no longer imported at all
    (asserted directly, not just via the framework-isolation test).
  - `_json_blob_spans` on a brace-free 600-char template: 56us -> 0.1us;
    `substitute_env_vars` 89us -> 33us. In-blob JSON escaping verified still applied.
  - `MapNode` row expression built once per map instead of once per row.
- **Deviations:**
  - SKIPPED `render(check=False)` on the client/server request paths. It is a real
    62us -> 3.4us win, but it trades away the guarantee that a user-supplied AST which
    cannot round-trip raises `RenderError` instead of silently executing different text.
    Against network-bound LLM calls the saving is noise, so this is an API decision
    (e.g. an opt-in `verify=` flag) rather than a silent cleanup. Recorded on OME-536.
  - The `GuardNode` generalization landed as an OPTIONAL capability protocol
    (`SupportsChildren` + `node_children`), matching the existing
    `SupportsFetchEx`/`SupportsHoldings` idiom. A required `children()` on the `DagNode`
    protocol would have broken the `runtime_checkable` isinstance checks for every
    existing node, since nodes conform structurally rather than by inheritance.
  - Architectural findings (dual compile pipelines, wire codec in `core/`, `_reassemble`
    param round-trip, `cli/_serve` re-deriving node routing rules, `MapNode`/`ReduceNode`
    structure->text round-trip, `RelUrlNode.is_expr`, no cross-run compile cache) were
    left untouched by design and are itemized on the issue.
