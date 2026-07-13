# Plan — url4 SDK facades

Spec: `docs/spec/2026-07-13-url4-sdk-facades.md`. Branch: `url4-sdk-facades`.
Order is dependency order; each gap is one TDD cycle (RED → GREEN → gates → commit).

## Baseline (verified)

385 tests green, ruff/format/pyright clean (venv rebuilt — stale shebangs from a
moved checkout). Working tree carries unrelated uncommitted v0.2 WIP; only files this
unit touches get committed.

## G1 — renderer (`src/url4/render.py`, ~350 lines)

1. `errors.py`: add `RenderError(Url4Error)` (code `unrenderable`).
2. `grammar.py`: add public `parse_value(text)` → `_parse_value` wrapper.
3. `render.py` internals:
   - `render(node, *, check=True)` — top-level; parenthesizes composite source nodes
     (Binding/Source/RelExpr/RemoteExpr); check = `build(out)` equality against the
     `Expression(sources=(node,))` wrap rule.
   - `_render_source` (Binding | Source | value), `_render_value` (leaf + Expression +
     Iteration-sans-reducer + RelExpr/RemoteExpr), `_render_intent` (Text quoted,
     Url/RelUrl verbatim), `_render_descriptor` (name:weight:budgets:binding;annots,
     `*` prefix for expand), `_render_struct_annotation` (depth ≤ 2),
     `_render_struct_object` (dict → `{…}`), `_format_number`.
   - Leaf validation via `_scan` helpers (depth-0 `,;!`, quotes, balanced parens).
   - Dual-key boundary guard: Source(value ∈ {Expression, RelExpr, RemoteExpr}) whose
     first annotation key is dual-scope and not preceded by an exclusive source key →
     RenderError (§8.1.2 would reclassify on reparse).
4. Tests `tests/test_render.py`: per-node golden cases; error cases; round-trip corpus
   (~60 hand-curated expressions covering every spec construct: descriptors, struct
   weights/budgets, expansion, iteration ± reduce ± directives, broadcast, @/@id,
   varrefs with paths, struct objects, rel/remote sugar+canonical, params, quoting);
   seeded random AST generator (~200 cases) asserting `build(render(x)) == wrap(x)`.

## G2 — builders (`src/url4/builders.py`, ~300 lines)

Constructors per spec; every builder result must satisfy `render(node, check=True)`.
Tests `tests/test_builders.py`: golden builder→render strings (the spec §4.5 examples
reproduced via builders); coercion matrix (str/Node/Mapping/list); intent
restrictions; validation errors; iterate-with-reduce embedding rewrite.

## G3 — client (`src/url4/client.py`, ~250 lines)

`Url4Result` + `Client` per spec. Tests `tests/test_client.py` over `StaticIOLayer`
(routes keyed `url4://host/v1` for remote); result envelope fields; env seeding;
aclose lifecycle (owned vs injected io); request string is canonical + reparseable.

## G4 — node SDK (`src/url4/server.py`, ~420 lines; split `_server_asgi.py` if >450)

Registries + dispatch + ASGI per spec. `pyproject.toml`: `[project.optional-dependencies]
server = ["uvicorn>=0.30"]`. Tests `tests/test_server.py`: endpoint decorator dispatch
(sync + async handlers); eval-path evaluation closing the client loop (Client → node
ASGI via `httpx.ASGITransport` → processor endpoint); holdings/identity incl. error
codes; data routes; outbound delegation (injected fake); ASGI status mapping
(200/400/404/403/405/502); GET-only.

## Finalize

`__init__.py` exports + quickstart; full gates; design-reviewer pass (this plan +
spec as rubric); ledger outcome; commits:
`feat(url4): expression renderer` → `feat(url4): builder facade` →
`feat(url4): client facade + result envelope` → `feat(url4): node SDK + ASGI shim`
(docs/ledger in the first commit it accompanies).

## Risk register

- **Renderer completeness** — mitigated by check-on-render + corpus + random ASTs.
- **§8.1.2 dual-key boundary** — explicit RenderError, tested.
- **Hoisting quirk** — top-level composites parenthesized, tested.
- **Engine wire convention (opaque context)** — endpoint handlers get raw context;
  only eval path re-evaluates; tested both ways.
- **File size** (sdlc ≤450 lines) — split points pre-identified.
- **Float formatting** — decimal-only formatter + check catches precision loss.
