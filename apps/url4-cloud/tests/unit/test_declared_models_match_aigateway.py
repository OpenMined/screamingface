"""The Runner's declared models must exist in aigateway's plugin registries.

Declaring endpoints buys deterministic routing; the cost is a second place to edit when a model
is added or removed. This guard makes that cost visible at CI time instead of at run time,
where a stale id becomes a `/v1/chat/completions` failure inside a user's expression.

The plugin lists are read with `ast` rather than imported: aigateway is a separate uv project
(pydantic, litellm) and is NOT installed in the url4-cloud test environment. Source-level
extraction keeps the guard dependency-free and honest about what it checks — the literal slug
lists, which is exactly what drifts.

Providers whose registries are built at runtime (ollama discovers a local host, openrouter and
huggingface read configured slugs) are undeclarable by construction and are not covered here.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PLUGINS = _REPO_ROOT / "apps/aigateway/src/aigateway/plugins"
_RUNNER_CONFIG = _REPO_ROOT / "apps/url4-cloud/backend/url4.toml"

# (source file, the assigned name holding the slug list, the gateway's id prefix).
# WHY anthropic has no prefix: its ModelEntry.model_name is the BARE slug — the `anthropic/`
# prefix appears only in litellm_params, so `/v1/models` advertises `claude-haiku-4-5`.
_SLUG_SOURCES = (
    ("anthropic_provider/settings.py", "names", ""),
    ("codex_provider/models.py", "_MODEL_SLUGS", "codex/"),
    ("gemini_provider/models.py", "_MODEL_SLUGS", "gemini-cli/"),
    ("antigravity_provider/settings.py", "names", "antigravity/"),
)


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


def _aigateway_model_ids() -> set[str]:
    ids: set[str] = set()
    for relative, name, prefix in _SLUG_SOURCES:
        source = _PLUGINS / relative
        assert source.is_file(), f"{source} moved — update _SLUG_SOURCES"
        ids.update(prefix + slug for slug in _string_list_assigned_to(source, name))
    return ids


def _declared_models() -> tuple[str, ...]:
    with _RUNNER_CONFIG.open("rb") as handle:
        return tuple(tomllib.load(handle)["aigateway"]["models"])


def test_the_guard_actually_finds_the_plugin_registries() -> None:
    # Without this, an upstream rename would empty the reference set and the subset assertion
    # below would pass vacuously — the guard would go green precisely when it should fail.
    ids = _aigateway_model_ids()

    assert len(ids) >= 10
    assert "claude-haiku-4-5" in ids
    assert "codex/gpt-5.5" in ids


def test_every_declared_model_exists_in_aigateway() -> None:
    declared = set(_declared_models())

    missing = sorted(declared - _aigateway_model_ids())

    assert missing == [], (
        f"backend/url4.toml declares model(s) aigateway does not serve: {missing}. "
        "Either the plugin list changed, or the id is misspelled — a declared route that "
        "resolves to nothing fails inside a user's expression, not at boot."
    )


@pytest.mark.parametrize("model", _declared_models())
def test_declared_model_ids_are_route_shaped(model: str) -> None:
    assert model, "empty model id"
    assert not model.startswith("/"), f"{model!r} must not start with '/' — routes derive it"
    assert model == model.strip(), f"{model!r} has surrounding whitespace"
