"""Stripping the base's own `[data]` table must stop at the NEXT header — including `[[…]]`.

FEATURE: a benchmark image merges generated artifact routes into the reviewed base config.
STORY: as a build, the merged file I ship declares everything the base declared, minus only the
`[data]` entries that are re-emitted from the fragments.

`_strip_data_table` drops the base's `[data]` section because `merge` re-renders those entries
alongside the generated ones. It decides where the section ENDS by watching for the next header —
but it only re-evaluated that flag on a SINGLE-bracket header, so an array-of-tables header
(`[[aigateway.models]]`) did not end the section and every line of it was dropped instead.

The base config carries no `[data]` table today, so nothing is currently lost. That is what makes
this worth pinning rather than leaving: the day a `[data]` entry is added above the model list,
the merged image silently loses model routes — and `_validate` only notices if `default_route`
happens to be among the casualties. A route that vanishes from a shipped image surfaces as
`endpoint_not_found` at the first expression that names it, long after the build that dropped it.

INVARIANT: `[[x]]` is a top-level header and ends the section, exactly as the docstring always
claimed. Only the literal `[data]` starts one — `[[data]]` is a different construct and must not.
"""

from __future__ import annotations

import tomllib

from url4_cloud.runner import merge_config

# `[data]` sits ABOVE the model list — legal TOML, and the shape that loses routes.
_BASE_WITH_DATA = """\
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"

[data]
"/motd" = "hand-written, re-emitted by the merge"

[[aigateway.models]]
id = "claude-haiku-4-5"

[[aigateway.models]]
id = "claude-opus-4-8"
web_tools = true

[commands]
"/read" = ["cat"]
"""

_FRAGMENT = """\
[data]
"/draco/cases" = { file = "/opt/b/cases.json", media_type = "application/json" }
"""


# The SILENT shape: one model is declared BEFORE `[data]`, so the survivors keep `models` a
# non-empty list and `_validate` sees a perfectly usable world — with routes missing from it.
_BASE_PARTIAL_LOSS = """\
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"

[[aigateway.models]]
id = "claude-haiku-4-5"

[data]
"/motd" = "hand-written"

[[aigateway.models]]
id = "openrouter/openai/gpt-5.5"
native_web_search = true
"""


def test_a_partial_loss_would_pass_validation_and_must_not_happen() -> None:
    """INVARIANT: this is why the bug is worth fixing rather than tolerating.

    When only the models AFTER `[data]` are dropped, `models` stays a non-empty list, the merged
    world parses, and the build reports success — shipping an image whose missing routes surface
    as `endpoint_not_found` at the first expression that names one. `_validate` cannot see it:
    a shorter list is not an invalid list.
    """
    merged = tomllib.loads(merge_config.merge(_BASE_PARTIAL_LOSS, [_FRAGMENT]))

    assert [m["id"] for m in merged["aigateway"]["models"]] == [
        "claude-haiku-4-5",
        "openrouter/openai/gpt-5.5",
    ]


def test_an_array_of_tables_header_ends_the_stripped_section() -> None:
    """The model routes declared after `[data]` must survive the merge."""
    merged = tomllib.loads(merge_config.merge(_BASE_WITH_DATA, [_FRAGMENT]))

    assert [m["id"] for m in merged["aigateway"]["models"]] == [
        "claude-haiku-4-5",
        "claude-opus-4-8",
    ]


def test_a_route_capability_declared_after_data_survives() -> None:
    """Not just the id — the capability flags beside it, which decide whether a route retrieves."""
    merged = tomllib.loads(merge_config.merge(_BASE_WITH_DATA, [_FRAGMENT]))
    opus = next(m for m in merged["aigateway"]["models"] if m["id"] == "claude-opus-4-8")

    assert opus["web_tools"] is True


def test_a_single_bracket_table_after_data_still_survives() -> None:
    """The case that already worked — pinned so the fix cannot regress it."""
    merged = tomllib.loads(merge_config.merge(_BASE_WITH_DATA, [_FRAGMENT]))

    assert merged["commands"]["/read"] == ["cat"]


def test_the_base_data_entry_is_re_emitted_not_lost() -> None:
    """Stripping is not deletion: `merge` re-renders the base's own entries with the generated
    ones, so a hand-written artifact route survives alongside them."""
    merged = tomllib.loads(merge_config.merge(_BASE_WITH_DATA, [_FRAGMENT]))

    assert merged["data"]["/motd"] == "hand-written, re-emitted by the merge"
    assert merged["data"]["/draco/cases"]["media_type"] == "application/json"


def test_only_one_data_table_is_emitted() -> None:
    """INVARIANT: the merged file has exactly one `[data]` header. Two would be a TOML redefinition
    error at the runner, i.e. a Job that dies at boot with the build reporting success."""
    merged_text = merge_config.merge(_BASE_WITH_DATA, [_FRAGMENT])

    assert merged_text.count("\n[data]") == 1
