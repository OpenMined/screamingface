# OME-859 — Declared model world implementation plan

> **For agentic workers:** use `superpowers:executing-plans` (or `subagent-driven-development`)
> to work task-by-task. Steps use `- [ ]` for tracking. The stack loop is `sdlc-python`.

**Goal:** Move url4-cloud's declared model list from `url4.toml` into a validated Python registry
that mirrors `benchmarks/`, and make CI fail when the registry and aigateway's compiled seeds
disagree in either direction.

**Architecture:** A new shared-leaf package `url4_cloud/models/` holds per-provider slug seeds, a
validating `ModelRegistry`, and one composition root `BUILTIN_MODEL_WORLD`. `world_config.load_config`
gains a defaulted `registry=` parameter and merges the registry (base world) with
`[[aigateway.models]]` (additive overlay). The drift guard flips from subset to set equality.

**Tech Stack:** Python 3.12+ · uv · pytest · pyright · ruff

**Spec:** `docs/spec/2026-08-17-OME-859-declared-model-world.md`
**Ledger:** `docs/work/2026-08-17-OME-859-declared-model-world.md`

## Global Constraints

- **Route-legal charset:** `ALPHA / DIGIT / "-" / "_" / "." / "~"` per segment (url4 spec §8). A
  `:` is illegal. 29 ids are therefore unroutable — spec F3, `OME-819`.
- **Canonical id rule (verbatim):** `slug if slug.startswith(f"{provider}/") else f"{provider}/{slug}"`.
  No per-provider exemption. This is the `OME-795` lesson — one rule, never a prefix table.
- **Route path invariant:** a route path is exactly `"/" + gateway_id`. No renaming, no aliases.
- **Gates (run from `apps/url4-cloud`):** `uv run .claude/scripts/run_gates.py url4-cloud` from the
  repo root, which runs: `ruff check` · `ruff format --check` · `pyright` ·
  `python3 ../../.claude/scripts/check_layering.py` ·
  `pytest --cov=url4_cloud --cov=url4.streaming --cov-fail-under=80 -q`
- **Tests are append-only.** Never weaken or delete a prior test. Modifying one is a 95%-gate STOP.
- **Commit body carries** `Refs: OME-859`. Never `Co-Authored-By`.
- **Files stay ≤450 lines.**
- **Semantic anchors only:** `WHY:` `INVARIANT:` `AIDEV-NOTE:` `FEATURE:` `STORY:`.
- **No layering-gate edit.** `models` is a shared leaf because it is named in neither
  `CONTROL_PLANE` nor `RUN_MODE`. If a task feels like it needs a gate edit, STOP.

## File structure

| File | Responsibility |
|---|---|
| `models/registry.py` (create) | `ROUTE_ID_RE`, `is_route_legal`, `ProviderSeed`, `ModelRegistry`, `EMPTY_MODEL_WORLD`. Owns the charset and the canonical rule. Imports **nothing** from `url4_cloud` — it is the leaf. |
| `models/seeds/*.py` (create ×6) | One `ProviderSeed` each, authored as slugs, mirroring one aigateway plugin list. |
| `models/builtins.py` (create) | `BUILTIN_MODEL_WORLD` — the single composition root. |
| `models/__init__.py` (create) | Public surface re-exports. |
| `world_config.py` (modify) | Imports the charset from `models.registry` and the default from `models.builtins`; merges; validates `default_route`. |
| `url4.toml` (modify) | Knobs only; `[[aigateway.models]]` optional + additive. |

**Import direction (acyclic, deliberate):** `world_config → models.builtins → models.registry`.
`models.registry` must never import `world_config`. This is why the charset regex moves *down*
into `registry.py` rather than being imported *up* from `world_config` — the other direction is a
cycle, because `world_config` needs `BUILTIN_MODEL_WORLD` as a parameter default.

---

## Task 1: The model registry

**Files:**
- Create: `apps/url4-cloud/src/url4_cloud/models/__init__.py`
- Create: `apps/url4-cloud/src/url4_cloud/models/registry.py`
- Test: `apps/url4-cloud/tests/unit/test_model_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ROUTE_ID_RE: re.Pattern[str]`
  - `is_route_legal(model_id: str) -> bool`
  - `ProviderSeed(provider: str, slugs: tuple[str, ...])`, frozen, with `.ids() -> tuple[str, ...]`
  - `ModelRegistry(seeds: Iterable[ProviderSeed] = ())` with properties
    `routable: frozenset[str]`, `aigateway_only: frozenset[str]`, `all_ids: frozenset[str]`,
    and `__len__`
  - `EMPTY_MODEL_WORLD: ModelRegistry`

- [ ] **Step 1: Write the failing tests**

```python
"""The declared model registry — canonicalisation, validation, and the colon partition."""

from __future__ import annotations

import pytest

from url4_cloud.models.registry import (
    EMPTY_MODEL_WORLD,
    ModelRegistry,
    ProviderSeed,
    is_route_legal,
)


def test_a_bare_slug_is_canonicalised_with_its_provider_prefix() -> None:
    registry = ModelRegistry((ProviderSeed("anthropic", ("claude-opus-5",)),))

    assert registry.routable == frozenset({"anthropic/claude-opus-5"})


def test_an_already_qualified_slug_is_left_untouched() -> None:
    # INVARIANT: prefixing is idempotent. Without this every OpenRouter id would gain a
    # second prefix (`openrouter/openrouter/openai/...`) — the OME-795 failure class.
    registry = ModelRegistry(
        (ProviderSeed("openrouter", ("openrouter/openai/gpt-5.5", "openai/gpt-5.4")),)
    )

    assert registry.routable == frozenset(
        {"openrouter/openai/gpt-5.5", "openrouter/openai/gpt-5.4"}
    )


def test_the_same_id_from_two_seeds_is_refused() -> None:
    seeds = (
        ProviderSeed("anthropic", ("claude-opus-5",)),
        ProviderSeed("anthropic", ("anthropic/claude-opus-5",)),
    )

    with pytest.raises(ValueError, match="duplicate model id"):
        ModelRegistry(seeds)


def test_a_colon_bearing_id_is_partitioned_rather_than_refused() -> None:
    # INVARIANT: a `:` is illegal in a url4 path segment (spec §8), so these ids can never be
    # routes. They are still declared, so the guard can assert set equality against aigateway
    # and OME-819 has a precise work-list.
    registry = ModelRegistry(
        (ProviderSeed("huggingface", ("openai/gpt-oss-120b:cerebras", "openai/gpt-oss-20b")),)
    )

    assert registry.aigateway_only == frozenset({"huggingface/openai/gpt-oss-120b:cerebras"})
    assert registry.routable == frozenset({"huggingface/openai/gpt-oss-20b"})


def test_all_ids_is_the_union_of_both_partitions() -> None:
    registry = ModelRegistry(
        (ProviderSeed("huggingface", ("org/a:novita", "org/b")),)
    )

    assert registry.all_ids == registry.routable | registry.aigateway_only
    assert len(registry) == 2


@pytest.mark.parametrize("slug", ["has space", "has%percent", "has#hash", "has?query"])
def test_an_id_illegal_for_a_reason_other_than_a_colon_is_refused(slug: str) -> None:
    # WHY raise rather than partition: a colon is a KNOWN, tracked grammar limit with real ids
    # behind it. Any other illegal character is a typo, and silently filing it under
    # `aigateway_only` would hide it from the equality guard forever.
    with pytest.raises(ValueError, match="not a valid URL4 expression path"):
        ModelRegistry((ProviderSeed("openrouter", (slug,)),))


def test_an_empty_slug_is_refused() -> None:
    with pytest.raises(ValueError, match="empty model id"):
        ModelRegistry((ProviderSeed("openrouter", ("",)),))


def test_a_slug_may_not_start_with_a_slash() -> None:
    with pytest.raises(ValueError, match="must not start with '/'"):
        ModelRegistry((ProviderSeed("openrouter", ("/openai/gpt-5.5",)),))


def test_the_empty_world_is_a_valid_registry() -> None:
    assert len(EMPTY_MODEL_WORLD) == 0
    assert EMPTY_MODEL_WORLD.all_ids == frozenset()


def test_route_legality_is_a_pure_function_of_the_id() -> None:
    assert is_route_legal("openrouter/openai/gpt-5.5")
    assert is_route_legal("claude-haiku-4-5")
    assert not is_route_legal("huggingface/org/model:novita")
```

- [ ] **Step 2: Run the tests and confirm they fail for the right reason**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_model_registry.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'url4_cloud.models'`.

- [ ] **Step 3: Write the minimal implementation**

`models/registry.py`:

```python
"""The declared model world as code — which gateway ids this Engine may route.

WHY code rather than the `[[aigateway.models]]` TOML array it replaces: the list must track
aigateway's compiled plugin seeds, which grew from 25 to 113 ids in one epic (OME-815) with
nothing in CI reporting the drift. Authoring it here makes the list type-checked, lets the
colon partition below be one predicate instead of 29 silent omissions, and gives the drift
guard a single object to compare against aigateway's source.

This module mirrors `url4_cloud/benchmarks/registry.py`: a validated immutable registry, one
composition root beside it (`builtins.py`), and all validation at construction — before the
first paid request.

INVARIANT: this module imports nothing from `url4_cloud`. `world_config` imports the charset
and `builtins` imports the seeds, so any import back up would be a cycle.

AIDEV-NOTE: a seed declares SLUGS, not ids. `ProviderSeed.ids()` applies aigateway's one
canonical rule. Keep it that way — each seed file then stays a byte-comparable mirror of the
plugin list it tracks, which is what `test_declared_models_match_aigateway.py` asserts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

ROUTE_ID_RE = re.compile(r"[A-Za-z0-9\-_.~]+(?:/[A-Za-z0-9\-_.~]+)*", re.ASCII)
"""A gateway id that is also renderable as a URL4 expression path (url4 spec §8).

INVARIANT: this is the ONE definition of the charset. `world_config` imports it rather than
keeping a second copy, because a route path is exactly `"/" + id` and the two rules cannot be
allowed to disagree.
"""

_COLON = ":"


def is_route_legal(model_id: str) -> bool:
    """Whether ``model_id`` can be a url4 route path segment-for-segment."""
    return ROUTE_ID_RE.fullmatch(model_id) is not None


def canonical_id(provider: str, slug: str) -> str:
    """The public id aigateway advertises for ``slug``.

    INVARIANT: mirrors `aigateway.core.model_capabilities.canonical_model_id` — keep the slug
    when it already begins with ``<provider>/``, otherwise prefix it. There is NO per-provider
    exemption; OME-795 was caused by a hand-written prefix table that guessed ``""`` for
    Anthropic, so all five Anthropic routes vanished from the projected catalog.
    """
    prefix = f"{provider}/"
    return slug if slug.startswith(prefix) else f"{prefix}{slug}"


@dataclass(frozen=True, slots=True)
class ProviderSeed:
    """One aigateway provider's compiled model list, authored as slugs."""

    provider: str
    slugs: tuple[str, ...]

    def ids(self) -> tuple[str, ...]:
        return tuple(canonical_id(self.provider, slug) for slug in self.slugs)


class ModelRegistry:
    """One immutable, validated set of gateway ids this Engine declares.

    FEATURE: the declared world — what a url4 expression may address and what
    ``GET /v1/models`` may advertise.
    """

    __slots__ = ("_aigateway_only", "_routable")

    def __init__(self, seeds: Iterable[ProviderSeed] = ()) -> None:
        routable: set[str] = set()
        aigateway_only: set[str] = set()
        for seed in seeds:
            for model_id in seed.ids():
                _validate(model_id)
                if model_id in routable or model_id in aigateway_only:
                    raise ValueError(f"duplicate model id {model_id!r}")
                if _COLON in model_id:
                    aigateway_only.add(model_id)
                else:
                    routable.add(model_id)
        self._routable = frozenset(routable)
        self._aigateway_only = frozenset(aigateway_only)

    @property
    def routable(self) -> frozenset[str]:
        """Ids that become url4 routes."""
        return self._routable

    @property
    def aigateway_only(self) -> frozenset[str]:
        """Ids aigateway serves that url4 cannot route, because they carry a ``:``.

        INVARIANT: never routed and never advertised. Declared anyway so the drift guard can
        assert set equality against aigateway's seeds, and so OME-819 has an exact work-list.
        """
        return self._aigateway_only

    @property
    def all_ids(self) -> frozenset[str]:
        return self._routable | self._aigateway_only

    def __len__(self) -> int:
        return len(self._routable) + len(self._aigateway_only)


def _validate(model_id: str) -> None:
    """Raise unless ``model_id`` is a well-formed gateway id.

    WHY a colon is tolerated here but every other illegal character is not: the colon is a
    known grammar limit with 29 real ids behind it, handled by the partition. Anything else is
    a typo, and filing a typo under `aigateway_only` would hide it from the equality guard.
    """
    if not model_id:
        raise ValueError("empty model id")
    if model_id.startswith("/"):
        raise ValueError(
            f"model id {model_id!r} must not start with '/' — the route path is derived as '/' + id"
        )
    if not is_route_legal(model_id.replace(_COLON, "")):
        raise ValueError(
            f"model id {model_id!r} is not a valid URL4 expression path — each segment may "
            "contain only ASCII letters, digits, '-', '_', '.', or '~'"
        )


EMPTY_MODEL_WORLD = ModelRegistry()
"""A world declaring nothing — the parallel of `benchmarks.EMPTY_BENCHMARKS`."""

__all__ = [
    "EMPTY_MODEL_WORLD",
    "ROUTE_ID_RE",
    "ModelRegistry",
    "ProviderSeed",
    "canonical_id",
    "is_route_legal",
]
```

`models/__init__.py`:

```python
"""The declared model world. See `registry.py` for the invariants."""

from url4_cloud.models.registry import (
    EMPTY_MODEL_WORLD,
    ROUTE_ID_RE,
    ModelRegistry,
    ProviderSeed,
    canonical_id,
    is_route_legal,
)

__all__ = [
    "EMPTY_MODEL_WORLD",
    "ROUTE_ID_RE",
    "ModelRegistry",
    "ProviderSeed",
    "canonical_id",
    "is_route_legal",
]
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_model_registry.py -q
```

Expected: all pass. Note `_validate` strips colons before the charset check, so
`is_route_legal` stays the honest public predicate while `_validate` accepts the colon.

- [ ] **Step 5: Commit**

```bash
git add apps/url4-cloud/src/url4_cloud/models apps/url4-cloud/tests/unit/test_model_registry.py
git commit -F - <<'EOF'
feat(url4-cloud): add the declared model registry

A validated immutable registry of gateway ids, mirroring benchmarks/registry.py:
all validation at construction, and colon-bearing ids partitioned into
aigateway_only rather than refused, because a ':' cannot appear in a url4 path
segment (spec §8).

Owns the route charset so world_config can import one definition instead of
keeping a second copy.

Refs: OME-859
EOF
```

---

## Task 2: The provider seeds and the composition root

**Files:**
- Create: `apps/url4-cloud/src/url4_cloud/models/seeds/__init__.py`
- Create: `apps/url4-cloud/src/url4_cloud/models/seeds/{anthropic,codex,gemini_cli,antigravity,openrouter,huggingface}.py`
- Create: `apps/url4-cloud/src/url4_cloud/models/builtins.py`
- Test: `apps/url4-cloud/tests/unit/test_model_seeds.py`

**Interfaces:**
- Consumes: `ProviderSeed`, `ModelRegistry` from Task 1.
- Produces: `BUILTIN_MODEL_WORLD: ModelRegistry` (113 ids: 84 routable, 29 `aigateway_only`).

**Transcription is script-bootstrapped, then owned by hand.** Do not hand-type 113 ids.

- [ ] **Step 1: Write the failing test**

```python
"""The shipped model world — shape and totals. Parity with aigateway is asserted by
tests/unit/test_declared_models_match_aigateway.py, which reads the plugin source."""

from __future__ import annotations

from url4_cloud.models.builtins import BUILTIN_MODEL_WORLD


def test_the_shipped_world_declares_every_compiled_provider() -> None:
    providers = {model_id.partition("/")[0] for model_id in BUILTIN_MODEL_WORLD.all_ids}

    assert providers == {
        "anthropic",
        "antigravity",
        "codex",
        "gemini-cli",
        "huggingface",
        "openrouter",
    }


def test_the_shipped_world_totals_match_the_audited_gap() -> None:
    # INVARIANT: 113 compiled ids, 29 of them colon-bearing (24 HuggingFace + 5 OpenRouter
    # `:batch`/`:free`). Audited 2026-08-17 against the plugin seeds; the equality guard is
    # what keeps this true, this test is what makes a change visible.
    assert len(BUILTIN_MODEL_WORLD) == 113
    assert len(BUILTIN_MODEL_WORLD.routable) == 84
    assert len(BUILTIN_MODEL_WORLD.aigateway_only) == 29


def test_the_default_route_is_routable() -> None:
    # INVARIANT: url4.toml's default_route must resolve. OME-795 shipped a default_route that
    # no declared model matched; it failed inside a user's expression, not at boot.
    assert "anthropic/claude-haiku-4-5" in BUILTIN_MODEL_WORLD.routable


def test_the_pinned_benchmark_judges_are_routable() -> None:
    # INVARIANT: a different judge materially changes benchmark scores (DRACO arXiv:2602.11685
    # §4.2 pins its judge; healthbench/definition.py pins JUDGE_MODEL). Both must stay routes.
    assert "openrouter/google/gemini-3.1-pro-preview" in BUILTIN_MODEL_WORLD.routable
    assert "openrouter/openai/gpt-5.4" in BUILTIN_MODEL_WORLD.routable


def test_every_huggingface_id_is_aigateway_only() -> None:
    # WHY: every HF router id pins a `:<provider>` backend, so all 24 are colon-blocked. The
    # url4.toml footer used to claim HF was "undeclarable by construction" because it built its
    # list at runtime — PR #583 gave it 24 compiled seeds, so the colon is the only reason now.
    hf = {i for i in BUILTIN_MODEL_WORLD.all_ids if i.startswith("huggingface/")}

    assert hf and hf <= BUILTIN_MODEL_WORLD.aigateway_only
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_model_seeds.py -q
```

Expected: `ModuleNotFoundError: No module named 'url4_cloud.models.builtins'`.

- [ ] **Step 3: Bootstrap the seed files with a throwaway script**

Write this to the scratchpad (NOT the repo), run it once, then delete it. It reuses the same
`ast` extraction the drift guard uses, so the seed files start byte-identical to the plugin lists.

```python
# scratchpad/bootstrap_seeds.py — run once, then delete. Not a committed generator (spec D4).
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # adjust to the repo root
PLUGINS = ROOT / "apps/aigateway/src/aigateway/plugins"
OUT = ROOT / "apps/url4-cloud/src/url4_cloud/models/seeds"

ASSIGNED = (
    ("anthropic_provider/settings.py", "names", "anthropic", "ANTHROPIC", "anthropic"),
    ("codex_provider/models.py", "_MODEL_SLUGS", "codex", "CODEX", "codex"),
    ("gemini_provider/models.py", "_MODEL_SLUGS", "gemini-cli", "GEMINI_CLI", "gemini_cli"),
    ("antigravity_provider/settings.py", "names", "antigravity", "ANTIGRAVITY", "antigravity"),
)
RETURNED = (
    ("openrouter_provider/settings.py", "_default_model_slugs", "openrouter", "OPENROUTER", "openrouter"),
    ("huggingface_provider/settings.py", "_default_model_slugs", "huggingface", "HUGGINGFACE", "huggingface"),
)


def _strings(node):
    items = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return items if items and len(items) == len(node.elts) else None


def assigned(src, name):
    for n in ast.walk(ast.parse(src.read_text())):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.List):
            if any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
                if (items := _strings(n.value)) is not None:
                    return items
    raise SystemExit(f"no `{name} = [...]` in {src}")


def returned(src, name):
    for n in ast.walk(ast.parse(src.read_text())):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            for s in ast.walk(n):
                if isinstance(s, ast.Return) and isinstance(s.value, ast.List):
                    if (items := _strings(s.value)) is not None:
                        return items
    raise SystemExit(f"no `def {name}` returning a list in {src}")


TEMPLATE = '''"""{provider} model seeds — mirrors `aigateway/plugins/{rel}`.

Slugs are copied verbatim from that list, so the two can be compared by eye. The canonical
`{provider}/` prefix is applied by `ProviderSeed.ids()`, never written here.

AIDEV-NOTE: when aigateway's list changes, `test_declared_models_match_aigateway.py` fails
until this tuple matches. Add or remove the slug; do not touch the guard.
"""

from url4_cloud.models.registry import ProviderSeed

{const} = ProviderSeed(
    provider="{provider}",
    slugs=(
{slugs}    ),
)

__all__ = ["{const}"]
'''

for rel, name, provider, const, module in ASSIGNED + RETURNED:
    src = PLUGINS / rel
    slugs = assigned(src, name) if (rel, name, provider, const, module) in ASSIGNED else returned(src, name)
    body = "".join(f'        "{s}",\n' for s in slugs)
    (OUT / f"{module}.py").write_text(
        TEMPLATE.format(provider=provider, rel=rel, const=const, slugs=body)
    )
    print(f"{module}.py — {len(slugs)} slugs")
```

Run it, then write `models/seeds/__init__.py`:

```python
"""Per-provider model seeds, each mirroring one aigateway plugin list."""
```

and `models/builtins.py`:

```python
"""The model world this url4-cloud deployment declares.

WHY a composition module: the registry machinery does not know which providers exist, exactly
as `benchmarks/builtins.py` keeps protocol-neutral registry code from importing concrete
protocols. This is the ONE place a deployment chooses its declared model world.

INVARIANT: this world is EXHAUSTIVE over aigateway's COMPILED seeds — every id its plugins
declare appears here, and `test_declared_models_match_aigateway.py` asserts set equality.
Exhaustive does NOT mean "everything a deployment serves": AIGW_OPENROUTER_DEFAULT_MODELS and
AIGW_HUGGINGFACE_DEFAULT_MODELS replace their lists at deploy time, and ollama discovers its
models at run time with no compiled list. Those deployments add entries via url4.toml.

AIDEV-NOTE: a declared route is NOT an enabled deployment. OpenRouter sits behind
AIGW_OPENROUTER_ENABLED; a route whose provider is disabled or uncredentialed resolves here and
then fails at the gateway, inside the user's expression. That is the accepted cost of declaring
the full compiled set (spec §6 consequence 1).
"""

from url4_cloud.models.registry import ModelRegistry
from url4_cloud.models.seeds.anthropic import ANTHROPIC
from url4_cloud.models.seeds.antigravity import ANTIGRAVITY
from url4_cloud.models.seeds.codex import CODEX
from url4_cloud.models.seeds.gemini_cli import GEMINI_CLI
from url4_cloud.models.seeds.huggingface import HUGGINGFACE
from url4_cloud.models.seeds.openrouter import OPENROUTER

BUILTIN_MODEL_WORLD = ModelRegistry(
    (ANTHROPIC, ANTIGRAVITY, CODEX, GEMINI_CLI, HUGGINGFACE, OPENROUTER)
)

__all__ = ["BUILTIN_MODEL_WORLD"]
```

- [ ] **Step 4: Run the tests, then delete the bootstrap script**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_model_seeds.py -q
```

Expected: all pass, with the totals 113 / 84 / 29. If a total differs, do **not** edit the test
— the audited numbers are the contract. Re-check the extraction against the plugin source.

- [ ] **Step 5: Commit**

```bash
git add apps/url4-cloud/src/url4_cloud/models apps/url4-cloud/tests/unit/test_model_seeds.py
git commit -F - <<'EOF'
feat(url4-cloud): seed the declared model world from every compiled provider

113 ids across six providers, 84 routable and 29 aigateway-only. Slugs are
copied verbatim from each aigateway plugin list so the two compare by eye; the
canonical prefix is applied by ProviderSeed.ids().

builtins.py is the single composition root, mirroring benchmarks/builtins.py.

Refs: OME-859
EOF
```

---

## Task 3: Merge the registry into the declared world

**Files:**
- Modify: `apps/url4-cloud/src/url4_cloud/world_config.py`
- Modify: `apps/url4-cloud/url4.toml`
- Test: `apps/url4-cloud/tests/unit/test_world_config_registry_merge.py`

**Interfaces:**
- Consumes: `BUILTIN_MODEL_WORLD`, `ModelRegistry`, `EMPTY_MODEL_WORLD`, `ROUTE_ID_RE`, `is_route_legal`.
- Produces: `load_config(env, *, registry: ModelRegistry = BUILTIN_MODEL_WORLD) -> WorldConfig`
  and `parse_config(raw, env, *, registry: ModelRegistry = BUILTIN_MODEL_WORLD) -> WorldConfig`.
  `declared_model_ids(env, *, registry=BUILTIN_MODEL_WORLD)` keeps its return type.

- [ ] **Step 1: Write the failing tests**

```python
"""The declared world is the registry, with url4.toml layered additively on top."""

from __future__ import annotations

import pytest

from url4_cloud.models.registry import EMPTY_MODEL_WORLD, ModelRegistry, ProviderSeed
from url4_cloud.world_config import WorldConfigError, parse_config, routes_for

_REGISTRY = ModelRegistry(
    (
        ProviderSeed("anthropic", ("claude-haiku-4-5", "claude-opus-5")),
        ProviderSeed("huggingface", ("org/model:novita",)),
    )
)


def _world(table: dict[str, object], registry: ModelRegistry = _REGISTRY):
    section = parse_config({"aigateway": table}, {}, registry=registry).aigateway
    assert section is not None
    return section


def test_registry_ids_reach_the_declared_world_without_any_toml_entry() -> None:
    section = _world({"default_route": "/anthropic/claude-haiku-4-5"})

    assert {m.id for m in section.models} == {
        "anthropic/claude-haiku-4-5",
        "anthropic/claude-opus-5",
    }


def test_a_toml_entry_may_add_an_id_the_registry_lacks() -> None:
    # WHY additive: ollama discovers its models at run time and two provider seed lists are
    # env-overridable, so a deployment must still be able to declare its own routes.
    section = _world(
        {
            "default_route": "/anthropic/claude-haiku-4-5",
            "models": [{"id": "ollama/llama-4"}],
        }
    )

    assert "ollama/llama-4" in {m.id for m in section.models}


def test_a_toml_entry_overrides_the_registry_capability_for_that_id() -> None:
    section = _world(
        {
            "default_route": "/anthropic/claude-haiku-4-5",
            "models": [{"id": "anthropic/claude-opus-5", "web_search": False}],
        }
    )

    specs = {m.id: m for m in section.models}
    assert specs["anthropic/claude-opus-5"].web_search is False
    assert specs["anthropic/claude-haiku-4-5"].web_search is True


def test_a_toml_entry_duplicating_a_registry_id_yields_exactly_one_spec() -> None:
    # INVARIANT: routes_for maps "/" + id, so two specs for one id would collapse silently and
    # whichever lost would take its capability with it.
    section = _world(
        {
            "default_route": "/anthropic/claude-haiku-4-5",
            "models": [{"id": "anthropic/claude-opus-5", "web_search": False}],
        }
    )

    ids = [m.id for m in section.models]
    assert ids.count("anthropic/claude-opus-5") == 1
    assert len(routes_for(section.models)) == len(ids)


def test_an_aigateway_only_id_never_enters_the_world() -> None:
    section = _world({"default_route": "/anthropic/claude-haiku-4-5"})

    assert "huggingface/org/model:novita" not in {m.id for m in section.models}


def test_a_default_route_declared_only_by_the_registry_validates() -> None:
    # INVARIANT: the OME-795 failure mode — a default_route no model matched failed inside a
    # user's expression rather than at boot.
    section = _world({"default_route": "/anthropic/claude-opus-5"})

    assert section.default_model == "anthropic/claude-opus-5"


def test_a_default_route_naming_an_aigateway_only_id_is_refused() -> None:
    with pytest.raises(WorldConfigError, match="cannot be a route"):
        _world({"default_route": "/huggingface/org/model:novita"})


def test_a_toml_only_world_still_builds_against_the_empty_registry() -> None:
    # Backward compatibility for a deployment pointing URL4_RUNNER_CONFIG at its own file.
    section = _world(
        {"default_route": "/ollama/llama-4", "models": [{"id": "ollama/llama-4"}]},
        EMPTY_MODEL_WORLD,
    )

    assert {m.id for m in section.models} == {"ollama/llama-4"}


def test_a_world_that_would_declare_nothing_is_refused() -> None:
    with pytest.raises(WorldConfigError, match="at least one model"):
        _world({"default_route": "/x"}, EMPTY_MODEL_WORLD)
```

- [ ] **Step 2: Run and confirm failure**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_world_config_registry_merge.py -q
```

Expected: `TypeError: parse_config() got an unexpected keyword argument 'registry'`.

- [ ] **Step 3: Modify `world_config.py`**

Six edits.

**3a.** Replace the local charset with the registry's, and import the default world. Delete
`_MODEL_ID_RE` (line 59) and add to the imports:

```python
from url4_cloud.models.builtins import BUILTIN_MODEL_WORLD
from url4_cloud.models.registry import ROUTE_ID_RE, ModelRegistry
```

In `_model_id`, replace `_MODEL_ID_RE.fullmatch(model)` with `ROUTE_ID_RE.fullmatch(model)`.

**3b.** Fix the false `provider_of` INVARIANT. Replace lines 85-100 with:

```python
def provider_of(model_id: str) -> str:
    """The provider that serves a route: the segment before the first `/`.

    WHY the segment and not a substring of the whole id: `openrouter/anthropic/claude-opus-4.8`
    is an OpenRouter route and must take OpenRouter's envelope. A substring test hands it to
    any future `anthropic` entry and silently sends it down the wrong provider's mechanism.

    INVARIANT: every gateway id carries its provider prefix. `canonical_model_id` has no
    per-provider exemption, so an unprefixed id names no provider and cannot be served — the
    equality guard in `test_declared_models_match_aigateway.py` is what makes that unreachable.

    AIDEV-NOTE: this used to fall back to `"anthropic"` for an id with no `/`, on the belief
    that aigateway advertised bare `claude-haiku-4-5`. That belief is what OME-795 was: the
    gateway serves `anthropic/claude-haiku-4-5`, so the fallback was unreachable for any real
    id while quietly mis-attributing any bare id that reached it.
    """
    prefix, separator, _ = model_id.partition("/")
    if not separator:
        raise WorldConfigError(
            f"model id {model_id!r} names no provider — every gateway id is "
            "'<provider>/<slug>' (aigateway's canonical_model_id has no exemption)"
        )
    return prefix
```

Delete `_UNPREFIXED_PROVIDER` (line 85).

**3c.** Thread `registry` through the three public entry points:

```python
def declared_model_ids(
    env: Mapping[str, str], *, registry: ModelRegistry = BUILTIN_MODEL_WORLD
) -> frozenset[str]:
    section = load_config(env, registry=registry).aigateway
    if section is None:
        return frozenset()
    return frozenset(model.id for model in section.models)


def load_config(
    env: Mapping[str, str], *, registry: ModelRegistry = BUILTIN_MODEL_WORLD
) -> WorldConfig:
    path = Path(env.get(job_env.RUNNER_CONFIG, DEFAULT_CONFIG_PATH))
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorldConfigError(f"cannot read world config {str(path)!r}: {exc}") from exc
    return parse_config(raw, env, registry=registry)


def parse_config(
    raw: Mapping[str, object],
    env: Mapping[str, str],
    *,
    registry: ModelRegistry = BUILTIN_MODEL_WORLD,
) -> WorldConfig:
    """Validate a parsed TOML mapping into a :class:`WorldConfig`. Fail-fast.

    INVARIANT: `registry` is the base world and the TOML array layers on top. Both halves call
    through here, so the App's discovery and the Runner's routes cannot diverge.
    """
    _reject_unsupported_tables(raw)
    table = raw.get("aigateway")
    if table is None:
        return WorldConfig()
    if not isinstance(table, Mapping):
        raise WorldConfigError(f"[aigateway] must be a table, got {table!r}")
    return WorldConfig(aigateway=_parse_aigateway(table, env, registry))
```

**3d.** Merge inside `_parse_aigateway`. Replace `models = _models(table.get("models"))` with:

```python
    models = _merge(registry, _declared_models(table.get("models")))
```

and pass `registry` into the signature: `def _parse_aigateway(table, env, registry) -> AigatewaySection:`.
After `section = _apply_env(section, env)`, replace the single `_require_declared` call with:

```python
    _reject_unroutable_default(section.default_model, registry)
    _require_declared(section.default_model, models)
```

**3e.** Replace `_models` (lines 259-272) with these three functions:

```python
def _declared_models(value: object) -> tuple[ModelSpec, ...]:
    """The `[[aigateway.models]]` array — OPTIONAL, because the registry is the base world.

    WHY it stayed: ollama discovers its models at run time and two provider seed lists are
    env-overridable (AIGW_OPENROUTER_DEFAULT_MODELS, AIGW_HUGGINGFACE_DEFAULT_MODELS), so a
    deployment must be able to declare a route the compiled registry cannot know about.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        raise WorldConfigError(f"[aigateway] models must be a list, got {value!r}")
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in value:
        spec = _model_spec(entry)
        if spec.id in seen:
            raise WorldConfigError(f"[aigateway] declares duplicate model id {spec.id!r}")
        seen.add(spec.id)
        models.append(spec)
    return tuple(models)


def _merge(registry: ModelRegistry, declared: tuple[ModelSpec, ...]) -> tuple[ModelSpec, ...]:
    """The registry's routable ids, with the TOML array layered on top.

    INVARIANT: exactly one spec per id. `routes_for` maps `"/" + id`, so a second spec for one
    id would collapse silently and whichever lost would take its capability with it.

    A TOML entry for a registry id REPLACES that spec, which is how `web_search = false`
    reaches a compiled route. A TOML entry for an unknown id is appended. Nothing removes an
    id: the declared world is exhaustive over the compiled seeds (spec D1).
    """
    merged: dict[str, ModelSpec] = {model_id: ModelSpec(id=model_id) for model_id in sorted(registry.routable)}
    for spec in declared:
        merged[spec.id] = spec
    if not merged:
        raise WorldConfigError(
            "[aigateway] declares at least one model neither in the built-in world nor in "
            "[[aigateway.models]] — a world with no routes can serve nothing"
        )
    return tuple(merged.values())


def _reject_unroutable_default(default_model: str, registry: ModelRegistry) -> None:
    """A `default_route` naming an `aigateway_only` id can never resolve.

    WHY a distinct error: `_require_declared` would report it as "not a declared model" beside
    a list of 84 ids, which reads like a typo. The real cause is that the id carries a `:` and
    no url4 path segment may (spec §8, OME-819).
    """
    if default_model in registry.aigateway_only:
        raise WorldConfigError(
            f"default_route {'/' + default_model!r} cannot be a route — the gateway serves "
            "this model but its id contains ':', which no URL4 path segment may contain"
        )
```

**3f.** Bound the `_require_declared` error message — 84 ids in one string is unreadable:

```python
def _require_declared(default_model: str, models: tuple[ModelSpec, ...]) -> None:
    ids = sorted(model.id for model in models)
    if default_model not in ids:
        shown = ids[:10]
        suffix = f" (+{len(ids) - len(shown)} more)" if len(ids) > len(shown) else ""
        raise WorldConfigError(
            f"default_route {'/' + default_model!r} is not a declared model — "
            f"declared: {shown}{suffix}"
        )
```

Add `ModelSpec`, `ModelRegistry`, `provider_of` as needed to `__all__`.

- [ ] **Step 4: Strip the model stanzas from `url4.toml`**

Delete every `[[aigateway.models]]` block (lines 50-153 of the current file) and the header
paragraphs that describe declaring models. Keep the `[aigateway]` knobs and the RESERVED note.
The header becomes:

```toml
# url4-cloud — the declared world, read by BOTH the Runner (what a run may address) and the App
# (what `GET /v1/models` advertises). One file, so discovery cannot promise what execution refuses.
#
# The MODEL LIST LIVES IN CODE: `url4_cloud/models/builtins.py::BUILTIN_MODEL_WORLD`, seeded from
# every aigateway provider plugin and held to it by set equality in
# `tests/unit/test_declared_models_match_aigateway.py` (OME-859). It moved there because this array
# had drifted to 25 ids while the gateway served 113, with nothing in CI reporting it.
#
# `[[aigateway.models]]` is still accepted and is ADDITIVE: an entry may declare a route the
# compiled world cannot know about (ollama discovers its models at run time;
# AIGW_OPENROUTER_DEFAULT_MODELS and AIGW_HUGGINGFACE_DEFAULT_MODELS replace their seed lists at
# deploy time), or may set `web_search = false` on a compiled route. It cannot remove one.
#
# `web_search` says only THAT a route searches, never HOW — the mechanism is derived from the
# provider by `world_config.provider_of` against `world_config.WEB_SEARCH_NATIVE_PROVIDERS`. It
# also enables nothing by itself where the Tavily loop is used: the deployment must supply
# TAVILY_API_KEY, or the route serves plain completions.

[aigateway]
base_url = "http://127.0.0.1:9105"
default_route = "/anthropic/claude-haiku-4-5"
timeout_s = 600.0
web_tool_max_iterations = 12
allow_outbound = true

# RESERVED — the format carries these (they are `url4 serve`'s tables) but the Runner does not
# parse them yet; declaring one is a loud config error, never a silent no-op:
#
#   [data]        "/corpus/papers" = { file = "…", media_type = "application/json" }
#   [commands]    "/python" = ["python3", "/opt/tools/run.py", "{intent}"]
#   [holdings]    default = { file = "…" }
#   [identities]
```

- [ ] **Step 5: Run the affected suites**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_world_config_registry_merge.py \
  tests/unit/test_runner_config.py tests/unit/test_web_search_routing.py \
  tests/unit/test_draco_lineup_declared.py tests/unit/test_executable_model_routes.py -q
```

Expected: the new file passes. If a prior test fails, read it before touching anything — under
the append-only rule, a prior test that must change is a **95% STOP**. A failure caused by the
world now being larger (a count or an exact-set assertion) is exactly such a case: report it and
ask, do not edit.

- [ ] **Step 6: Commit**

```bash
git add apps/url4-cloud/src/url4_cloud/world_config.py apps/url4-cloud/url4.toml \
  apps/url4-cloud/tests/unit/test_world_config_registry_merge.py
git commit -F - <<'EOF'
feat(url4-cloud): merge the model registry into the declared world

load_config takes the registry as the base world and layers [[aigateway.models]]
on top additively, in the one parser both halves already call — so discovery and
execution cannot diverge. url4.toml keeps its knobs and loses its 25 stanzas.

Also removes provider_of's unreachable "anthropic" fallback, whose INVARIANT
still asserted the unprefixed-Anthropic belief that OME-795 disproved.

Refs: OME-859
EOF
```

---

## Task 4: Flip the drift guard to set equality

**Files:**
- Modify: `apps/url4-cloud/tests/unit/test_declared_models_match_aigateway.py`

**Interfaces:**
- Consumes: `BUILTIN_MODEL_WORLD`.
- Produces: nothing.

This task modifies an existing test file. That is permitted here and only here: the spec's D6 is
an owner-approved change to this guard, recorded in the ledger's Deviations. **Assertions are
added and strengthened; none is weakened or deleted.**

- [ ] **Step 1: Add the sixth extraction source and the equality assertions**

Keep `_canonical`, `_string_list_assigned_to`, `_string_list_returned_by` and the existing
`test_the_canonical_rule_prefixes_once_and_only_once` untouched. Add HuggingFace to
`_RETURNED_SLUG_SOURCES`:

```python
_RETURNED_SLUG_SOURCES = (
    ("openrouter_provider/settings.py", "_default_model_slugs", "openrouter"),
    # OME-859: HuggingFace was absent from this table because it had no compiled list when the
    # guard was written. PR #583 gave it 24 seeds, so 24 served ids were invisible here.
    ("huggingface_provider/settings.py", "_default_model_slugs", "huggingface"),
)
```

Replace `_declared_models()`/`_declared_default_route()`'s TOML reads with registry reads, and
add:

```python
def test_the_declared_world_is_exactly_what_aigateway_serves() -> None:
    """INVARIANT: set equality, not containment — the property the old subset check lacked.

    A subset assertion is why 88 served models became undeclarable while CI stayed green
    (OME-815 grew the seeds from 25 to 113). Equality fails in both directions: a typo shows up
    as declared-but-not-served, a missed seed PR as served-but-not-declared.
    """
    served = _aigateway_model_ids()
    declared = set(BUILTIN_MODEL_WORLD.all_ids)

    assert declared - served == set(), (
        f"declared but not served: {sorted(declared - served)} — a typo, or aigateway dropped "
        "the model. A declared route that resolves to nothing fails inside a user's expression."
    )
    assert served - declared == set(), (
        f"served but not declared: {sorted(served - declared)} — add each slug to the matching "
        "url4_cloud/models/seeds/ module. An undeclared model cannot be addressed at all."
    )


def test_the_unroutable_ids_are_exactly_the_colon_bearing_ones() -> None:
    """INVARIANT: the partition is a pure function of the id, and nothing renames an id to
    dodge it. A route path is exactly '/' + the gateway id — no aliases (spec D3)."""
    served = _aigateway_model_ids()

    assert BUILTIN_MODEL_WORLD.aigateway_only == {i for i in served if ":" in i}
    assert BUILTIN_MODEL_WORLD.routable == {i for i in served if ":" not in i}


def test_the_unroutable_set_is_pinned() -> None:
    """The OME-819 work-list, as reviewable text. Growing it must be a conscious edit."""
    assert len(BUILTIN_MODEL_WORLD.aigateway_only) == 29
    assert sum(1 for i in BUILTIN_MODEL_WORLD.aigateway_only if i.startswith("huggingface/")) == 24
    assert sum(1 for i in BUILTIN_MODEL_WORLD.aigateway_only if i.startswith("openrouter/")) == 5
```

Extend the non-vacuity test to all six sources:

```python
def test_the_guard_actually_finds_the_plugin_registries() -> None:
    ids = _aigateway_model_ids()

    assert len(ids) >= 100
    assert "anthropic/claude-haiku-4-5" in ids
    assert "codex/gpt-5.5" in ids
    assert "openrouter/openai/gpt-5.5" in ids
    # OME-859: the HuggingFace extractor is the one that would newly contribute nothing.
    assert any(i.startswith("huggingface/") for i in ids)
    for provider in ("anthropic", "antigravity", "codex", "gemini-cli", "huggingface", "openrouter"):
        assert any(i.startswith(f"{provider}/") for i in ids), f"{provider} extraction is stale"
```

Add the migration guard, which may be deleted once merged:

```python
# The 25 ids url4.toml declared before OME-859. Every one must still be routable: a route id
# that changed or vanished breaks live expressions, and two of these are score-affecting
# benchmark judge pins.
_PRE_OME859_DECLARED = frozenset({
    "anthropic/claude-opus-4-8", "anthropic/claude-opus-4-7", "anthropic/claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-5", "anthropic/claude-haiku-4-5",
    "codex/gpt-5.5", "codex/gpt-5.4", "codex/gpt-5.4-mini", "codex/gpt-5.3-codex", "codex/gpt-5.2",
    "gemini-cli/gemini-3.1-flash-lite", "gemini-cli/gemini-2.5-pro",
    "gemini-cli/gemini-2.5-flash", "gemini-cli/gemini-2.5-flash-lite",
    "antigravity/gemini-3-flash",
    "openrouter/openai/gpt-5.5", "openrouter/openai/gpt-5.4",
    "openrouter/anthropic/claude-opus-4.8", "openrouter/anthropic/claude-fable-5",
    "openrouter/anthropic/claude-haiku-4.5", "openrouter/google/gemini-3.1-pro-preview",
    "openrouter/google/gemini-3-flash-preview", "openrouter/moonshotai/kimi-k2.6",
    "openrouter/deepseek/deepseek-v4-pro", "openrouter/qwen/qwen3.6-plus",
})


def test_no_previously_declared_route_disappeared() -> None:
    missing = sorted(_PRE_OME859_DECLARED - BUILTIN_MODEL_WORLD.routable)

    assert missing == [], f"these routes existed before OME-859 and must not vanish: {missing}"
```

- [ ] **Step 2: Run the guard**

```bash
cd apps/url4-cloud && uv run pytest tests/unit/test_declared_models_match_aigateway.py -q
```

Expected: PASS. A `served - declared` failure means a seed module is incomplete — fix the seed,
never the assertion.

- [ ] **Step 3: Run the full gates**

```bash
cd /home/junior/workspace/screamingface/.claude/worktrees/OME-859-declared-model-world
uv run .claude/scripts/run_gates.py url4-cloud
```

Expected: ruff · format · pyright · **check_layering** · pytest ≥80% coverage all green.
`check_layering.py` must pass with **no edit** — `models` is a shared leaf because it is named in
neither `CONTROL_PLANE` nor `RUN_MODE`. If it fails, STOP: something imported across the halves.

- [ ] **Step 4: Update the ledger Outcome and commit**

Fill Actual files / Commits / Gates / Deviations in
`docs/work/2026-08-17-OME-859-declared-model-world.md`. Deviations must record: the guard file
was modified (owner-approved D6), and `provider_of`'s fallback removal (a public-behaviour change
found mid-implementation).

```bash
git add apps/url4-cloud/tests/unit/test_declared_models_match_aigateway.py \
  docs/work/2026-08-17-OME-859-declared-model-world.md
git commit -F - <<'EOF'
test(url4-cloud): hold the declared world to aigateway by set equality

The guard asserted only declared subset-of served, so OME-815 grew the gateway
from 25 to 113 ids with 88 of them undeclarable and CI green. Equality fails in
both directions, and adds the HuggingFace extraction source the table never had.

Pins the 29 colon-bearing ids as the OME-819 work-list and asserts no
pre-existing route disappeared.

Refs: OME-859
EOF
```

---

## Self-review

**Spec coverage.** D1 → Task 2 (all compiled ids seeded). D2 → Tasks 1-2. D3 → Task 1 partition +
Task 4 pin. D4 → Task 2 Step 3 (throwaway, deleted). D5 → Task 3 `_declared_models`/`_merge` +
the rewritten TOML. D6 → Task 4. D7 → nothing to build (rejected). §4.3 one merge point → Task 3d.
§4.4 all four guard changes → Task 4. §5 error handling → Task 3e/3f. §6 consequence 3 → Task 4
migration guard. §7 every named assertion appears in a task.

**Type consistency.** `ModelRegistry.routable/aigateway_only/all_ids` are `frozenset[str]`
throughout. `ProviderSeed.ids()` returns `tuple[str, ...]`. `_merge` takes
`(ModelRegistry, tuple[ModelSpec, ...])` and returns `tuple[ModelSpec, ...]`, matching
`AigatewaySection.models`. `registry=` is keyword-only with the same default on all three public
entry points.

**Known open risk.** Task 3 Step 5 may find a prior test asserting an exact declared-model set or
count. That is a 95%-gate STOP by rule 5, not an edit — the plan deliberately does not pre-authorise
changing it.


---

## Execution record (filled during implementation)

Counts re-audited at the branch base `f4684a83`: **117** compiled ids, **88** routable, **29**
colon-blocked, `url4.toml` declaring **32**. The plan's 113 / 84 / 29 / 25 came from an audit at
`e431b715`, before `OME-856` landed 4 more OpenRouter seeds. Task 2's totals test carries the
corrected numbers; the `_PRE_OME859_DECLARED` migration set carries 32 ids, not 25.

Two deviations from the plan as written:

1. **Task 3 step 3b was reverted.** Removing `provider_of`'s `"anthropic"` fallback is pinned by
   `test_web_search_routing.py`, so it is a prior-test change outside this unit's approved scope.
   The behaviour is restored and an `AIDEV-NOTE` records that the `INVARIANT` is doubtful and the
   fallback appears unreachable. Worth its own ticket.
2. **The registry default stayed `BUILTIN_MODEL_WORLD`.** The plan implied injecting at the
   composition roots with an empty default (the `EMPTY_BENCHMARKS` precedent). Measured: an empty
   default fails 25 prior tests versus 10 for a built-in default, because many prior tests read the
   shipped `url4.toml` for its list. A built-in default is also the fail-safe choice — a caller who
   forgets to inject gets the correct world rather than a silently route-less one. The 10 affected
   tests were fixed at their **module-level helpers** (`_parse`, `_section`, `_parse_models`,
   `_config`), so no assertion inside any test body changed. The append-only gate confirms this: it
   flags only the guard file, whose change is owner-approved D6.
