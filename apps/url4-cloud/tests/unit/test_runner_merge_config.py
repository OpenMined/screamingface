"""Merging generated `[data]` fragments into the hand-written `url4.toml`.

FEATURE: a benchmark image ships its artifacts as declared routes.
STORY: as a build, I combine the human-authored config with N generated fragments into the one
file `runner/config.py` reads, and I fail HERE rather than shipping an image that fails at boot.

INVARIANT: validation runs against the REAL parser (`runner.config.parse_config`), not a
lookalike. A merged file that this accepts but the runner rejects would turn a build-time error
into a Job that dies after the client already attached.
"""

from __future__ import annotations

import tomllib

import pytest

from url4_cloud.runner import merge_config

_BASE = """\
# a comment the merge must preserve
[aigateway]
base_url = "http://aigateway.test"
# INVARIANT: the runner's default route lives INSIDE [aigateway]; there is no top-level form.
# It is the node's `default_processor`, i.e. the JUDGE in a benchmark image.
default_route = "/claude-haiku-4-5"
models = ["claude-haiku-4-5"]

[commands]
"/read" = ["cat"]
"""

_FRAGMENT = """\
[data]
"/draco/cases" = { file = "/opt/b/cases.json", media_type = "application/json" }
"/draco/rubrics/1" = { file = "/opt/b/rubrics/1.json" }
"""


def _merged_table(*fragments: str) -> dict:
    return tomllib.loads(merge_config.merge(_BASE, list(fragments)))


# --- the merge ------------------------------------------------------------------


def test_the_base_tables_survive() -> None:
    merged = _merged_table(_FRAGMENT)

    assert merged["aigateway"]["models"] == ["claude-haiku-4-5"]
    assert merged["commands"]["/read"] == ["cat"]
    assert merged["aigateway"]["default_route"] == "/claude-haiku-4-5"


def test_the_fragment_routes_are_added() -> None:
    merged = _merged_table(_FRAGMENT)

    assert merged["data"]["/draco/cases"]["media_type"] == "application/json"
    assert "/draco/rubrics/1" in merged["data"]


def test_base_comments_are_preserved() -> None:
    """The base is human-authored and reviewed; the merge must not strip its reasoning."""
    assert "# a comment the merge must preserve" in merge_config.merge(_BASE, [_FRAGMENT])


def test_several_fragments_combine_into_one_data_table() -> None:
    """TOML allows a table name ONCE, so two `[data]` sections cannot simply be concatenated."""
    second = '[data]\n"/mmlu/cases" = { file = "/opt/m/cases.json" }\n'

    merged = _merged_table(_FRAGMENT, second)

    assert {"/draco/cases", "/draco/rubrics/1", "/mmlu/cases"} <= set(merged["data"])


def test_no_fragments_leaves_the_base_unchanged() -> None:
    assert merge_config.merge(_BASE, []) == _BASE


def test_a_base_that_already_declares_data_is_merged_not_duplicated() -> None:
    base = _BASE + '\n[data]\n"/motd" = "hi"\n'

    merged = tomllib.loads(merge_config.merge(base, [_FRAGMENT]))

    assert merged["data"]["/motd"] == "hi"
    assert "/draco/cases" in merged["data"]


# --- fail at build, not at boot -------------------------------------------------


def test_a_route_colliding_with_a_command_is_rejected() -> None:
    """The runner rejects this at boot; catching it here fails the BUILD instead of shipping an
    image whose Jobs die after a client has already attached."""
    bad = '[data]\n"/read" = "x"\n'

    with pytest.raises(merge_config.MergeError, match="already declared"):
        merge_config.merge(_BASE, [bad])


def test_a_route_colliding_with_a_model_is_rejected() -> None:
    bad = '[data]\n"/claude-haiku-4-5" = "x"\n'

    with pytest.raises(merge_config.MergeError, match="already declared"):
        merge_config.merge(_BASE, [bad])


def test_the_same_route_in_two_fragments_is_rejected() -> None:
    """Silently keeping the last one would make the served rubric depend on fragment order."""
    with pytest.raises(merge_config.MergeError, match="/draco/cases"):
        merge_config.merge(_BASE, [_FRAGMENT, _FRAGMENT])


def test_a_fragment_carrying_a_non_data_table_is_rejected() -> None:
    """A generated fragment declares artifacts and nothing else — a stray `[commands]` in one
    would let generated content redefine executable routes."""
    with pytest.raises(merge_config.MergeError, match="only"):
        merge_config.merge(_BASE, ['[commands]\n"/evil" = ["sh"]\n'])


def test_malformed_toml_in_a_fragment_is_rejected() -> None:
    with pytest.raises(merge_config.MergeError, match="cannot parse"):
        merge_config.merge(_BASE, ["[data\n"])


def test_the_merged_file_is_validated_by_the_real_runner_parser() -> None:
    """A base whose `default_route` names an undeclared model is a runner error, so the merge
    must surface it even though the fragment itself is fine."""
    base = _BASE.replace('default_route = "/claude-haiku-4-5"', 'default_route = "/absent"')

    with pytest.raises(merge_config.MergeError):
        merge_config.merge(base, [_FRAGMENT])
