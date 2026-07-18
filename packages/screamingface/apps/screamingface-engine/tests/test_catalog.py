from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from screamingface import Case, Grader

from screamingface_engine import catalog, cli


def test_gpqa_loader_normalizes_and_stably_shuffles_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def load_dataset(*args: object, **kwargs: object):
        calls.append((args, kwargs))
        return [
            {
                "Question": "Which is correct?",
                "Correct Answer": "correct",
                "Incorrect Answer 1": "wrong one",
                "Incorrect Answer 2": "wrong two",
                "Incorrect Answer 3": "wrong three",
            }
        ]

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=load_dataset))

    first = tuple(catalog.gpqa_cases())
    second = tuple(catalog.gpqa_cases())

    assert first == second
    assert first[0].id == "gpqa-diamond-0"
    assert first[0].reference in {"A", "B", "C", "D"}
    assert "Reply with only A, B, C, or D" in first[0].input
    assert calls[0] == (("Idavidrein/gpqa", "gpqa_diamond"), {"split": "train"})


def test_draco_loader_accepts_question_and_json_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def load_dataset(*_args: object, **_kwargs: object):
        return [
            {
                "id": "d1",
                "question": "Research this",
                "answer": json.dumps({"sections": []}),
                "metadata": json.dumps({"domain": "economics"}),
            },
            {
                "problem": "Fallback identifiers",
                "answer": {"sections": []},
                "domain": "medicine",
            },
        ]

    monkeypatch.setitem(sys.modules, "datasets", SimpleNamespace(load_dataset=load_dataset))

    cases = tuple(catalog.draco_cases())

    assert cases[0] == Case(
        "d1",
        "Research this",
        reference={"sections": []},
        metadata={"domain": "economics"},
    )
    assert cases[1].id == "draco-1"
    assert cases[1].metadata == {"domain": "medicine"}


def test_publications_reject_unknown_loader_and_serialize_both_graders() -> None:
    with pytest.raises(ValueError, match="unknown benchmark"):
        catalog.published_benchmarks({"other@1": lambda: ()})

    publications = catalog.published_benchmarks(
        {
            "gpqa@1": lambda: (Case("g", "question", reference="A"),),
            "draco@1": lambda: (Case("d", "question", reference={"sections": []}),),
        }
    )

    gpqa = catalog.manifest_document(publications[0])
    draco = catalog.manifest_document(publications[1])
    registry = catalog.registry_document(publications)

    assert gpqa["grader"] == {"type": "exact_choice"}
    draco_grader = draco["grader"]
    assert isinstance(draco_grader, dict)
    assert draco_grader["passes"] == 5
    benchmarks = registry["benchmarks"]
    assert isinstance(benchmarks, list)
    draco_entry = benchmarks[1]
    assert isinstance(draco_entry, dict)
    assert draco_entry["id"] == "draco@1"
    assert catalog.cases_document(publications[0]).endswith("\n")


def test_model_catalog_is_unique_and_does_not_claim_unimplemented_tools() -> None:
    publications = catalog.published_benchmarks({"gpqa@1": lambda: (), "draco@1": lambda: ()})
    registry = catalog.registry_document(publications)

    assert len({model.id for model in catalog.MODEL_ROUTES}) == len(catalog.MODEL_ROUTES)
    assert len({model.route for model in catalog.MODEL_ROUTES}) == len(catalog.MODEL_ROUTES)
    assert all(model.gateway_model for model in catalog.MODEL_ROUTES)
    assert registry["models"] == [
        {"id": model.id, "supported_tools": []} for model in catalog.MODEL_ROUTES
    ]
    assert registry["reducers"] == [{"id": "majority_vote", "route": "/reducers/majority-vote"}]


def test_catalog_rejects_an_unserializable_grader() -> None:
    class OtherGrader(Grader):
        kind = "other"

    with pytest.raises(TypeError, match="unsupported grader"):
        catalog._grader_document(OtherGrader())


@pytest.mark.parametrize(
    ("value", "expected"),
    [("not json", {}), ("[]", {}), ({"domain": "science"}, {"domain": "science"})],
)
def test_metadata_json_object_is_lenient(value: object, expected: dict[str, object]) -> None:
    assert catalog._json_object(value) == expected


def test_cli_serves_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, str, int]] = []
    app = object()
    run = Mock(side_effect=lambda value, *, host, port: calls.append((value, host, port)))
    monkeypatch.setattr(cli, "create_app", lambda *, settings: app)
    monkeypatch.setattr(cli.importlib, "import_module", lambda _name: SimpleNamespace(run=run))
    monkeypatch.setenv("URL4_HOST", "0.0.0.0")
    monkeypatch.setenv("URL4_PORT", "4500")

    cli.main()

    assert calls == [(app, "0.0.0.0", 4500)]
