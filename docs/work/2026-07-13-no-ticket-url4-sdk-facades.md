---
ticket: none (Linear filing explicitly waived by owner this session — "skip the linear task step")
stack: pkg/url4 (not yet registered in .claude/sdlc.local.md — card gap; gates run manually)
status: done
started: 2026-07-13
finished: 2026-07-13
---

# url4 SDK facades — renderer, builders, client, node

## Intent

Close the four product-surface gaps identified in the URL4 spec (Parts A+B) digest so the
`packages/url4` engine becomes usable as an SDK, matching the approved UX direction
(client-side `query/broadcast/iterate/reduce` helpers; node-side decorator-registered
endpoints + holdings with in-process/ASGI serving):

- **G1 renderer** — `render(node) -> str`, the missing inverse of `build()`/`parse()`;
  prerequisite for every builder.
- **G2 builders** — Python constructors (`expr`, `src`, `text`, `ref`, `self_`, `identity`,
  `iterate`, `broadcast`, `reduce`, `expand`) that lower to the existing frozen AST with
  grammar-faithful normalization.
- **G3 client** — `Client` + `Url4Result` envelope over `url4.run()`, local + remote
  (RemoteExpr wrapping), owned HttpIOLayer lifecycle.
- **G4 node SDK** — `Url4Node`: endpoint/holdings/identity registries implementing the
  IOLayer + SupportsHoldings ports (a node IS an io layer), `evaluate()`, framework-free
  ASGI shim (GET-only per url4-engine doctrine N1), lazy-uvicorn `serve()`.

## Planned changes

- `packages/url4/src/url4/render.py` (new) + `errors.py` (add `RenderError`) +
  `grammar.py` (public `parse_value()`)
- `packages/url4/src/url4/builders.py` (new)
- `packages/url4/src/url4/client.py` (new)
- `packages/url4/src/url4/node.py` (new; ASGI inline, uvicorn lazy)
- `packages/url4/src/url4/__init__.py` (exports; file already carries uncommitted v0.2 WIP)
- `packages/url4/tests/test_render.py`, `test_builders.py`, `test_client.py`,
  `test_node.py` (new)
- `docs/spec/2026-07-13-url4-sdk-facades.md`, `docs/plan/2026-07-13-url4-sdk-facades.md`

## Test plan

- **G1**: per-node render cases; round-trip property `build(render(x)) == x` over the
  full corpus of expression texts harvested from existing tests + seeded random AST
  generator; unrepresentable-value errors (unbalanced-paren URLs, negative weights,
  dual-key boundary misclassification) raise `RenderError` naming the leaf.
- **G2**: builder → render golden strings; coercions (str/dict/Node); two-axis kwargs;
  validation errors (required+optional, reserved names, bad weight).
- **G3**: Client over StaticIOLayer — query/broadcast/iterate/reduce results, remote
  target via fetch_map/routes, Url4Result.text/.data/.elements, aclose lifecycle.
- **G4**: Url4Node — endpoint dispatch (decorator), holdings/identity resolution incl.
  error codes (unknown_identity, identity_access_denied), evaluate() in-process, ASGI
  GET via httpx.ASGITransport (200 body, 400 parse error, 404 unknown path, 405 non-GET).

## Acceptance

- All four modules land with tests; prior 385 tests stay green and unmodified.
- Gates green: `uv run ruff check` · `uv run ruff format --check` · `uv run pyright` ·
  `uv run pytest -q` (in `packages/url4`).
- Round-trip property holds for every existing-corpus expression.
- Design-reviewer pass with the plan as rubric; STRUCTURAL findings resolved.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, with two renames/additions: the node SDK landed as
  `src/url4/server.py` (not `node.py` — avoids the `nodes.py`/`dag/node.py` name pileup)
  and the review relocated the dual-wire-convention decode into `subrequest.py`
  (`decode_subrequest_http` / `decode_expression_http`). Also touched (small, additive):
  `io_static.py` (routes accept canonical `?params&q=` forms), `grammar.py`
  (`parse_value`), `errors.py` (`RenderError`), `pyproject.toml` (`server` extra),
  `tests/test_public_api.py` (extra).
- **Commits:** d06c983 chore(url4): snapshot in-progress v0.2 working tree ·
  a7fb9ef feat(url4): expression renderer · a02844a feat(url4): builder facade ·
  e3e5177 feat(url4): client facade + StaticIOLayer canonical routes ·
  9233022 feat(url4): node SDK + ASGI shim · e2bd242 feat(url4): package exports ·
  (+ final commit: design-review fixes + docs)
- **Gates:** `uv run ruff check` ✓ · `ruff format --check` ✓ · `pyright` 0 errors ·
  `pytest` 585 passed (385 baseline, all green and unmodified; 200 new). Baseline venv
  had stale shebangs from a moved checkout — rebuilt before starting.
- **Design review:** design-reviewer verdict ACCEPT-WITH-FIXES, zero structural
  findings; applied F1 (wire decode moved to its single-owner codec module),
  F2/F3 (grammar `_STRUCT_KEY_RE` + `_annotations._VALID_ON_ERROR` reused), F4
  (`Url4Node(data=…)` restored), F8 (one identity-name rule); F5 resolved by amending
  the spec (`elements` raises ValueError), F6 spec corrected (quorum IS enforced).
- **Deviations:** Linear ticket + docs/tasks mirror waived by owner; url4 stack missing
  from sdlc card (gates run manually — card should gain a url4 entry); pre-existing
  uncommitted v0.2 WIP committed as its own base snapshot so every commit is a
  self-consistent checkout; `render.py` (633 lines) exceeds the skill's ≤450 guidance
  but matches package norms (grammar.py 739, dag/nodes.py 857).
- **Engine findings for the grammar owner (Kevin):** (1) top-level `/p(c)!'i'` /
  `url4://…(c)!'i'` HOISTS the intent to expression level — spec §3.1.1 reads as
  whole-expression-remote; (2) the envelope's reduce-over-iteration decode is greedy:
  `(…, A*(b)!'p')!'r'` swallows sibling sources into the collection prefix (silent
  data loss on some shapes) — consider requiring double parens for expression
  collections; (3) spec §5.3.1's direct `(expr)!'Clean'*(…)` form does not parse —
  engine needs `((expr)!'Clean')*(…)`; (4) unnamed structured weights and unnamed
  budget-first descriptors are parser-unreachable (sugar/value-shape capture) —
  worth a spec note.
