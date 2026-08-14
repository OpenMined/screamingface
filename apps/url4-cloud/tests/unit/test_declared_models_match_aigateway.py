"""The Runner's declared models must exist in aigateway's plugin registries.

Declaring endpoints buys deterministic routing; the cost is a second place to edit when a model
is added or removed. This guard makes that cost visible at CI time instead of at run time,
where a stale id becomes a `/v1/chat/completions` failure inside a user's expression.

The plugin lists are read with `ast` rather than imported: aigateway is a separate uv project
(pydantic, litellm) and is NOT installed in the url4-cloud test environment. Source-level
extraction keeps the guard dependency-free and honest about what it checks — the literal slug
lists, which is exactly what drifts.

Providers whose registries are built at runtime (ollama discovers a local host, huggingface
fetches router slugs) are undeclarable by construction and are not covered here.

OpenRouter sits between the two: its slugs ARE compiled into the plugin, as the seed list
`_default_model_slugs()` returns, but a deployment can replace them wholesale via
`AIGW_OPENROUTER_DEFAULT_MODELS`. It is covered against those seeds — that catches the typo
this guard exists for — with the standing caveat that a deployment which overrides the env var
has moved the target and is on its own.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGINS = _REPO_ROOT / "apps/aigateway/src/aigateway/plugins"
_RUNNER_CONFIG = _REPO_ROOT / "apps/url4-cloud/url4.toml"

# (source file, the assigned name holding the slug list, the plugin's `custom_llm_provider`).
#
# INVARIANT: the third field is the PROVIDER NAME, never a pre-computed prefix string. The
# gateway derives every public id through one universal rule (`canonical_model_id`), mirrored
# below in `_canonical` — so this table states only what the rule needs as input.
#
# AIDEV-NOTE: this used to carry a hand-written prefix per provider, with anthropic's set to ""
# on the belief that `/v1/models` advertised bare `claude-haiku-4-5`. `canonical_model_id` has
# no such exemption — it prefixes unless the slug already starts with `<provider>/` — so the
# gateway served `anthropic/claude-haiku-4-5` while url4.toml declared the bare form, all five
# Anthropic routes silently dropped out of the projected catalog, and the declared default_route
# failed with `model must be provider-prefixed`. Twenty-six tests passed throughout (OME-795).
# Do not reintroduce a per-provider prefix column: four independent guesses drift, one rule
# cannot.
_SLUG_SOURCES = (
    ("anthropic_provider/settings.py", "names", "anthropic"),
    ("codex_provider/models.py", "_MODEL_SLUGS", "codex"),
    ("gemini_provider/models.py", "_MODEL_SLUGS", "gemini-cli"),
    ("antigravity_provider/settings.py", "names", "antigravity"),
)

# (source file, the function whose `return [...]` holds the slugs, the `custom_llm_provider`).
# WHY a separate table: these slugs are returned by a default-factory function rather than
# bound to a module-level name, so the assignment scan below cannot see them. OpenRouter's seeds
# are already spelled as full gateway ids (`openrouter/<author>/…`), which is precisely the
# already-prefixed case `_canonical` leaves alone.
_RETURNED_SLUG_SOURCES = (
    ("openrouter_provider/settings.py", "_default_model_slugs", "openrouter"),
)


def _canonical(provider: str, slug: str) -> str:
    """The public id aigateway advertises for ``slug``, by aigateway's own rule.

    INVARIANT: mirrors `aigateway.core.model_capabilities.canonical_model_id` — keep the slug
    when it already begins with ``<provider>/``, otherwise prefix it. aigateway is a separate uv
    project and is NOT installed here, so this is a mirror rather than an import; it is one line
    of one rule, which is the smallest surface that can go stale.
    """
    prefix = f"{provider}/"
    return slug if slug.startswith(prefix) else f"{prefix}{slug}"


def _string_list_assigned_to(source: Path, name: str) -> tuple[str, ...]:
    """Every string literal in the first ``name = [...]`` assignment in ``source``."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        items = [
            e.value
            for e in node.value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if items and len(items) == len(node.value.elts):
            return tuple(items)
    raise AssertionError(f"no `{name} = [...]` string list found in {source} — the guard is stale")


def _string_list_returned_by(source: Path, name: str) -> tuple[str, ...]:
    """Every string literal in the first ``return [...]`` inside ``def name`` in ``source``."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != name:
            continue
        for statement in ast.walk(node):
            if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.List):
                continue
            items = [
                e.value
                for e in statement.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if items and len(items) == len(statement.value.elts):
                return tuple(items)
    raise AssertionError(f"no `def {name}` returning a string list in {source} — guard is stale")


def _aigateway_model_ids() -> set[str]:
    ids: set[str] = set()
    for relative, name, provider in _SLUG_SOURCES:
        source = _PLUGINS / relative
        assert source.is_file(), f"{source} moved — update _SLUG_SOURCES"
        ids.update(_canonical(provider, slug) for slug in _string_list_assigned_to(source, name))
    for relative, name, provider in _RETURNED_SLUG_SOURCES:
        source = _PLUGINS / relative
        assert source.is_file(), f"{source} moved — update _RETURNED_SLUG_SOURCES"
        ids.update(_canonical(provider, slug) for slug in _string_list_returned_by(source, name))
    return ids


def _declared_default_route() -> str:
    """The `default_route` url4.toml names, without its leading slash."""
    with _RUNNER_CONFIG.open("rb") as handle:
        return str(tomllib.load(handle)["aigateway"]["default_route"]).lstrip("/")


def _declared_models() -> tuple[str, ...]:
    """The route ids declared in url4.toml, in declaration order.

    Each `[[aigateway.models]]` entry is a table (`id` plus its capabilities); the bare-string
    shorthand the parser also accepts is normalized here so the guard covers both spellings.
    """
    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]
    return tuple(e if isinstance(e, str) else e["id"] for e in entries)


def test_the_guard_actually_finds_the_plugin_registries() -> None:
    # Without this, an upstream rename would empty the reference set and the subset assertion
    # below would pass vacuously — the guard would go green precisely when it should fail.
    ids = _aigateway_model_ids()

    assert len(ids) >= 10
    # Anthropic is prefixed like every other provider — `canonical_model_id` has no exemption.
    assert "anthropic/claude-haiku-4-5" in ids
    assert "codex/gpt-5.5" in ids
    # The returned-list extractor is the one that would silently contribute nothing.
    assert "openrouter/openai/gpt-5.5" in ids


def test_the_canonical_rule_prefixes_once_and_only_once() -> None:
    # INVARIANT: the mirrored rule is idempotent — an already-qualified slug (OpenRouter's
    # seeds) must survive untouched, or every OpenRouter id would gain a second prefix.
    assert _canonical("anthropic", "claude-haiku-4-5") == "anthropic/claude-haiku-4-5"
    assert _canonical("openrouter", "openrouter/openai/gpt-5.5") == "openrouter/openai/gpt-5.5"
    assert _canonical("codex", _canonical("codex", "gpt-5.5")) == "codex/gpt-5.5"


def test_the_declared_default_route_is_a_declared_model() -> None:
    """INVARIANT: the fan-out reduce dispatches here, so it must name a route that resolves.

    A default_route that no `[[aigateway.models]]` entry declares is unreachable: it fails at
    the gateway inside a user's expression rather than at boot (OME-795).
    """
    assert _declared_default_route() in set(_declared_models())


def test_every_declared_model_exists_in_aigateway() -> None:
    declared = set(_declared_models())

    missing = sorted(declared - _aigateway_model_ids())

    assert missing == [], (
        f"url4.toml declares model(s) aigateway does not serve: {missing}. "
        "Either the plugin list changed, or the id is misspelled — a declared route that "
        "resolves to nothing fails inside a user's expression, not at boot."
    )


@pytest.mark.parametrize("model", _declared_models())
def test_declared_model_ids_are_route_shaped(model: str) -> None:
    assert model, "empty model id"
    assert not model.startswith("/"), f"{model!r} must not start with '/' — routes derive it"
    assert model == model.strip(), f"{model!r} has surrounding whitespace"
