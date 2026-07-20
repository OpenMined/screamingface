"""Read-side registries for `url4 serve` (url4._serve): [data], [holdings], [identities].

STORY: as an operator I declare my node's read surface in url4.toml alongside my
[commands]: `[data]` routes serve plain reads (so bare relative URIs resolve),
`[holdings]` backs `@`, and `[identities.<name>]` backs `@name` — each from an
inline value, a live-read file, or an operator-owned command (doctrine N4 for
reads). Bad declarations fail before bind; missing shelves fail per-source with
the node's own error semantics.
"""

from __future__ import annotations

import pytest

from url4.cli._serve import ConfigError, ProviderSpec, ServeConfig, build_node, resolve
from url4.core.errors import ResolutionError

CMDS = {"/echo": ("cat",)}


def _resolve(tmp_path, toml_text: str):
    toml = tmp_path / "url4.toml"
    toml.write_text(toml_text, encoding="utf-8")
    return resolve({}, {}, toml)


BASE = '[commands]\n"/echo" = "cat"\n'


# --- parsing -----------------------------------------------------------------------


def test_provider_forms_parse(tmp_path) -> None:
    config = _resolve(
        tmp_path,
        BASE
        + "[data]\n"
        + '"/inline" = "plain text"\n'
        + '"/table" = { value = "tabled" }\n'
        + '"/filed" = { file = "corpus.md", media_type = "text/markdown" }\n'
        + '"/gen" = { command = ["printf", "x"] }\n',
    )
    assert config.data["/inline"] == ProviderSpec(value="plain text")
    assert config.data["/table"] == ProviderSpec(value="tabled")
    assert config.data["/filed"] == ProviderSpec(file="corpus.md", media_type="text/markdown")
    assert config.data["/gen"] == ProviderSpec(command=("printf", "x"))


def test_holdings_default_key_normalizes_to_none(tmp_path) -> None:
    config = _resolve(
        tmp_path, BASE + '[holdings]\ndefault = "MINE"\nscience = { value = "SCI" }\n'
    )
    assert config.holdings[None] == ProviderSpec(value="MINE")
    assert config.holdings["science"] == ProviderSpec(value="SCI")


def test_identities_parse_nested_shelves(tmp_path) -> None:
    config = _resolve(
        tmp_path,
        BASE + '[identities.emily]\ndefault = "E-DEFAULT"\nnotes = { value = "E-NOTES" }\n',
    )
    assert config.identities["emily"][None] == ProviderSpec(value="E-DEFAULT")
    assert config.identities["emily"]["notes"] == ProviderSpec(value="E-NOTES")


# --- declaration errors (fail before bind) -----------------------------------------


@pytest.mark.parametrize(
    ("snippet", "match"),
    [
        ('[data]\n"/x" = { }\n', "exactly one of value/file/command"),
        ('[data]\n"/x" = { value = "a", file = "b" }\n', "exactly one of value/file/command"),
        ('[data]\n"/x" = 5\n', "must be a string or a table"),
        ('[data]\n"/x" = { value = "a", nope = 1 }\n', "unknown keys"),
        ('[data]\n"/x" = { command = [] }\n', "has an empty command argv"),
        ('[holdings]\nscience = { value = "a", media_type = "text/csv" }\n', "unknown keys"),
        ('[identities.emily]\n"" = "x"\n', "collection name cannot be empty"),
    ],
)
def test_bad_provider_declarations(tmp_path, snippet: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        _resolve(tmp_path, BASE + snippet)


@pytest.mark.parametrize(
    ("prefix", "match"),
    [
        ('data = "not-a-table"\n', r"\[data\] must be a table"),
        ('holdings = "not-a-table"\n', r"\[holdings\] must be a table"),
        ('identities = "not-a-table"\n', r"\[identities\] must be a table"),
    ],
)
def test_registry_declared_as_scalar_is_rejected(tmp_path, prefix: str, match: str) -> None:
    # A registry key written as a scalar (`data = "x"`) instead of a table is a
    # plausible typo; it must fail as a clean pre-bind ConfigError. The scalar
    # goes BEFORE [commands] — a bare key after a table header would belong to
    # that table, not the document root.
    with pytest.raises(ConfigError, match=match):
        _resolve(tmp_path, prefix + BASE)


def test_identity_declared_as_scalar_is_rejected(tmp_path) -> None:
    with pytest.raises(ConfigError, match=r"\[identities.emily\] must be a table"):
        _resolve(tmp_path, BASE + '[identities]\nemily = "not-a-table"\n')


def test_validate_rejects_clashing_and_invalid_paths() -> None:
    spec = ProviderSpec(value="x")
    with pytest.raises(ConfigError, match="data path 'nope'"):
        ServeConfig(commands=CMDS, data={"nope": spec}).validate()
    with pytest.raises(ConfigError, match="clash with command routes"):
        ServeConfig(commands=CMDS, data={"/echo": spec}).validate()
    with pytest.raises(ConfigError, match="clash with reserved"):
        ServeConfig(commands=CMDS, data={"/healthz": spec}).validate()
    with pytest.raises(ConfigError, match="identity name '9bad!'"):
        ServeConfig(commands=CMDS, identities={"9bad!": {None: spec}}).validate()


# --- resolution behavior through the node ------------------------------------------

pytestmark_async = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_data_route_serves_bare_relative_uri() -> None:
    config = ServeConfig(commands=CMDS, data={"/rubrics/42": ProviderSpec(value="RUBRIC-42")})
    node = build_node(config)
    result = await node.evaluate("(/rubrics/42)!''")
    assert "RUBRIC-42" in result.text


@pytest.mark.asyncio
async def test_file_provider_reads_live(tmp_path) -> None:
    corpus = tmp_path / "corpus.md"
    corpus.write_text("FIRST", encoding="utf-8")
    config = ServeConfig(commands=CMDS, data={"/corpus": ProviderSpec(file=str(corpus))})
    node = build_node(config)
    assert "FIRST" in (await node.evaluate("(/corpus)!''")).text
    corpus.write_text("SECOND", encoding="utf-8")  # live: no rebuild, no restart
    assert "SECOND" in (await node.evaluate("(/corpus)!''")).text


@pytest.mark.asyncio
async def test_file_provider_missing_file_is_resolution_error(tmp_path) -> None:
    config = ServeConfig(
        commands=CMDS, data={"/gone": ProviderSpec(file=str(tmp_path / "missing.md"))}
    )
    node = build_node(config)
    with pytest.raises(ResolutionError, match="cannot be read"):
        await node.evaluate("(/gone)!''")


@pytest.mark.asyncio
async def test_media_type_drives_collection_parsing() -> None:
    # A one-line JSON array served as text/plain would line-split into ONE
    # element; the declared media type makes it parse as three (spec §5.3.7).
    rows = '[{"n": "a"}, {"n": "b"}, {"n": "c"}]'
    config = ServeConfig(
        commands=CMDS,
        data={"/rows": ProviderSpec(value=rows, media_type="application/json")},
    )
    node = build_node(config)
    result = await node.evaluate("(/rows*(x=$item.n, /echo(got: $item.n)!'noop')!'')")
    assert result.text.count("got:") == 3


@pytest.mark.asyncio
async def test_self_holdings_default_and_scoped_shelves() -> None:
    config = ServeConfig(
        commands=CMDS,
        holdings={None: ProviderSpec(value="DEFAULT-SHELF"), "sci": ProviderSpec(value="SCI")},
    )
    node = build_node(config)
    assert await node.fetch_holdings(None, None) == "DEFAULT-SHELF"
    assert await node.fetch_holdings(None, "sci") == "SCI"
    # Undeclared collection falls back to the default shelf (node semantics).
    assert await node.fetch_holdings(None, "other") == "DEFAULT-SHELF"


@pytest.mark.asyncio
async def test_identity_shelves_mirror_self_holdings_fallback() -> None:
    config = ServeConfig(
        commands=CMDS,
        identities={
            "emily": {None: ProviderSpec(value="E-DEF"), "notes": ProviderSpec(value="E-NOTES")},
            "andrew": {"published": ProviderSpec(value="A-PUB")},
        },
    )
    node = build_node(config)
    assert await node.fetch_holdings("emily", "notes") == "E-NOTES"
    assert await node.fetch_holdings("emily", "drafts") == "E-DEF"  # default fallback
    assert await node.fetch_holdings("andrew", "published") == "A-PUB"
    with pytest.raises(ResolutionError, match="serves no holdings"):
        await node.fetch_holdings("andrew", "private")  # no default shelf declared
    with pytest.raises(ResolutionError, match="unknown identity"):
        await node.fetch_holdings("nobody", None)  # node's own error, untouched


@pytest.mark.asyncio
async def test_command_provider_receives_collection_substitution() -> None:
    argv = ("python3", "-c", "import sys; sys.stdout.write('shelf=' + sys.argv[1])", "{collection}")
    config = ServeConfig(commands=CMDS, holdings={None: ProviderSpec(command=argv)})
    node = build_node(config)
    assert await node.fetch_holdings(None, "science") == "shelf=science"
    assert await node.fetch_holdings(None, None) == "shelf="


@pytest.mark.asyncio
async def test_holdings_resolve_through_expressions() -> None:
    # End-to-end: `@` and `@emily/notes` inside expressions, through the engine.
    config = ServeConfig(
        commands=CMDS,
        holdings={None: ProviderSpec(value="NODE-CORPUS")},
        identities={"emily": {"notes": ProviderSpec(value="EMILY-NOTES")}},
    )
    node = build_node(config)
    result = await node.evaluate("(@, @emily/notes)!'compare'")
    assert "NODE-CORPUS" in result.text
    assert "EMILY-NOTES" in result.text
