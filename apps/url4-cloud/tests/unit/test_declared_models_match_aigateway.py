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

# (source file, the assigned name holding the slug list, the gateway's canonical id prefix).
# AI Gateway's catalogue canonicalizes every bare provider model as ``<provider>/<model>``;
# Anthropic's bare ModelEntry names therefore advertise as ``anthropic/claude-haiku-4-5``.
_SLUG_SOURCES = (
    ("anthropic_provider/settings.py", "names", "anthropic/"),
    ("codex_provider/models.py", "_MODEL_SLUGS", "codex/"),
    ("gemini_provider/models.py", "_MODEL_SLUGS", "gemini-cli/"),
    ("antigravity_provider/settings.py", "names", "antigravity/"),
)

# (source file, the function whose `return [...]` holds the slugs, the gateway's id prefix).
# WHY a separate table: these slugs are returned by a default-factory function rather than
# bound to a module-level name, so the assignment scan below cannot see them. WHY the prefix is
# empty: OpenRouter's seeds are already spelled as full gateway ids (`openrouter/<author>/…`).
_RETURNED_SLUG_SOURCES = (("openrouter_provider/settings.py", "_default_model_slugs", ""),)


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
    for relative, name, prefix in _SLUG_SOURCES:
        source = _PLUGINS / relative
        assert source.is_file(), f"{source} moved — update _SLUG_SOURCES"
        ids.update(prefix + slug for slug in _string_list_assigned_to(source, name))
    for relative, name, prefix in _RETURNED_SLUG_SOURCES:
        source = _PLUGINS / relative
        assert source.is_file(), f"{source} moved — update _RETURNED_SLUG_SOURCES"
        ids.update(prefix + slug for slug in _string_list_returned_by(source, name))
    return ids


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
    assert "anthropic/claude-haiku-4-5" in ids
    assert "codex/gpt-5.5" in ids
    # The returned-list extractor is the one that would silently contribute nothing.
    assert "openrouter/openai/gpt-5.5" in ids


def test_every_declared_model_exists_in_aigateway() -> None:
    declared = set(_declared_models())

    missing = sorted(declared - _aigateway_model_ids())

    assert missing == [], (
        f"url4.toml declares model(s) aigateway does not serve: {missing}. "
        "Either the plugin list changed, or the id is misspelled — a declared route that "
        "resolves to nothing fails inside a user's expression, not at boot."
    )


def test_runner_allows_five_minutes_for_each_aigateway_request() -> None:
    with _RUNNER_CONFIG.open("rb") as handle:
        timeout_s = tomllib.load(handle)["aigateway"]["timeout_s"]

    assert timeout_s == 300


@pytest.mark.parametrize("model", _declared_models())
def test_declared_model_ids_are_route_shaped(model: str) -> None:
    assert model, "empty model id"
    assert not model.startswith("/"), f"{model!r} must not start with '/' — routes derive it"
    assert model == model.strip(), f"{model!r} has surrounding whitespace"


def test_no_route_declares_web_tools_it_cannot_use() -> None:
    # `web_tools` only means anything on a route that exists; a true on an id aigateway does
    # not serve is a config error the run would never reach, so catch it here.
    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]
    enabled = {e["id"] for e in entries if not isinstance(e, str) and e.get("web_tools")}

    assert enabled, "no route declares web_tools — the Tavily loop is now unreachable"
    assert sorted(enabled - _aigateway_model_ids()) == []
