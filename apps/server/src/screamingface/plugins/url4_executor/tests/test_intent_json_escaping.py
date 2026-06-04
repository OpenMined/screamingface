"""SF-235 (WI-1): JSON-escape ``$item``/``$var`` substitutions, but ONLY
when the token lands inside a ``{...}`` json_blob span.

A scored ensemble builds a per-row JSON intent like
``/python(/data/code/check_correct.py)!{"question":"$item.question",...}``.
When a model answer contains a control char (newline/tab) or a quote, a RAW
substitution makes the blob invalid JSON and ``json.loads`` raises downstream
(``python_runner/plugin.py``). These tests pin that values substituted inside
a ``{...}`` blob are JSON-escaped (so the blob round-trips), while values in
non-JSON positions (e.g. the prompt of ``/claude($item.question)``) stay RAW.
"""

import json

from screamingface.plugins.url4_executor.ensemble_helpers import (
    substitute_env_vars,
    substitute_item,
)
from screamingface.plugins.url4_executor.scope import Env


def test_item_field_with_newline_stays_valid_json_inside_blob() -> None:
    template = '/python(/data/code/check_correct.py)!{"q":"$item.question"}'
    item = json.dumps({"question": 'line1\nline2\twith\ttabs and "quotes"'})
    out = substitute_item(template, item)
    blob = out.split("!", 1)[1]
    assert json.loads(blob)["q"] == 'line1\nline2\twith\ttabs and "quotes"'


def test_item_field_outside_blob_is_not_escaped() -> None:
    template = "/claude($item.question)"
    item = json.dumps({"question": "what is 2\n+2?"})
    assert substitute_item(template, item) == "/claude(what is 2\n+2?)"


def test_env_var_with_control_char_escaped_inside_blob() -> None:
    env = Env.root().child(consensus="A\nB")
    out = substitute_env_vars('{"consensus":"$consensus"}', env)
    assert json.loads(out)["consensus"] == "A\nB"


def test_env_var_outside_blob_not_escaped() -> None:
    env = Env.root().child(name="x\ny")
    assert substitute_env_vars("hello $name", env) == "hello x\ny"


def test_mixed_blob_and_non_blob_item_fields() -> None:
    # Same field appears both inside the prompt (raw) and inside the JSON blob
    # (escaped). One pass must treat each occurrence by its own position.
    template = '/claude($item.q)!{"q":"$item.q"}'
    item = json.dumps({"q": 'a"b\nc'})
    out = substitute_item(template, item)
    prompt = out.split("!", 1)[0]
    blob = out.split("!", 1)[1]
    assert prompt == '/claude(a"b\nc)'
    assert json.loads(blob)["q"] == 'a"b\nc'


def test_item_non_string_field_inside_blob_stays_valid_json() -> None:
    template = '/python(/x.py)!{"score":$item.score,"q":"$item.q"}'
    item = json.dumps({"score": 42, "q": 'has "quote"'})
    out = substitute_item(template, item)
    blob = out.split("!", 1)[1]
    parsed = json.loads(blob)
    assert parsed["score"] == 42
    assert parsed["q"] == 'has "quote"'


def test_env_var_unknown_left_verbatim_inside_blob() -> None:
    env = Env.root().child(consensus="A")
    out = substitute_env_vars('{"c":"$consensus","m":"$missing"}', env)
    assert "$missing" in out
    assert json.loads(out)["c"] == "A"
