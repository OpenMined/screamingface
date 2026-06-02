from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall, Url4List, Url4Text
from screamingface.plugins.url4_executor.url4_grammar import parse


def test_json_blob_intent_parses_with_commas():
    node = parse('/python(/data/code/x.py)!{"a":"1","b":"2"}')
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == '{"a":"1","b":"2"}'


def test_list_with_json_blob_does_not_split_on_inner_commas():
    # The JSON's commas must NOT split the 2-element group.
    node = parse('(name=v, /python(/data/code/x.py)!{"a":"1","b":"2"})')
    assert isinstance(node, Url4List)
    assert len(node.items) == 2  # binding + backend_call (NOT 3+)
    bc = node.items[1]
    assert isinstance(bc, Url4BackendCall)
    assert isinstance(bc.intent, Url4Text)
    assert bc.intent.value == '{"a":"1","b":"2"}'


def test_one_level_nested_json_blob():
    node = parse('/python(/data/code/x.py)!{"a":{"b":"1"}}')
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == '{"a":{"b":"1"}}'


def test_non_brace_intent_still_text():
    node = parse("/claude(q)!hello world")
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "hello world"


def test_quoted_text_intent_unaffected():
    node = parse("/claude(q)!'answer concisely'")
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "'answer concisely'"
