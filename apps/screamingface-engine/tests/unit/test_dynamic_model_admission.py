"""OME-880: dynamic OpenRouter model admission — the engine half of OME-878.

FEATURE: run any OpenRouter model. On a model-parameters miss for an
OpenRouter-shaped id, the engine asks the gateway `POST /v1/models/admit`
before refusing. A grant joins an in-memory overlay beside the frozen declared
world (deployment lifetime), invalidates the catalog cache, and the fetch
proceeds; a refusal comes back as a gateway-shaped 404 body carrying the
diagnostic code; a gateway without the endpoint (or unreachable) degrades to
today's plain `ModelNotInstalled` — never a crash.

INVARIANT: the compiled declared world, the set-equality drift guard, and
url4.toml semantics are untouched — admission only ever ADDS, in memory.
"""

from __future__ import annotations

import json

import httpx
import pytest

from screamingface_engine import job_env
from screamingface_engine.catalog.admission import (
    AdmissionAnswer,
    AdmittedModels,
    is_dynamically_admissible,
)
from screamingface_engine.catalog.aigateway import AigatewayCatalogSource
from screamingface_engine.catalog.cache import CachedCatalog
from screamingface_engine.catalog.executable import ExecutableCatalog, ExecutableModelParameterSource
from screamingface_engine.catalog.port import (
    Credential,
    ModelCatalog,
    ModelNotInstalled,
    ModelParameterResponse,
    compute_etag,
)
from screamingface_engine.models.registry import EMPTY_MODEL_WORLD
from screamingface_engine.world_config import WorldConfigError, parse_config, routes_for

_DECLARED = "openrouter/openai/gpt-5.5"
_TARGET = "openrouter/qwen/qwen2.5-7b-instruct"
_CREDENTIAL = Credential.derive("default", {"X-User-Email": "alice@example.com"})


# --- the shape gate ----------------------------------------------------------


@pytest.mark.parametrize(
    "model_id",
    [_TARGET, "openrouter/mistralai/ministral-3b-2512"],
)
def test_openrouter_shaped_ids_are_admissible(model_id: str) -> None:
    assert is_dynamically_admissible(model_id)


@pytest.mark.parametrize(
    "model_id",
    [
        "anthropic/claude-haiku-4-5",  # not OpenRouter's namespace
        "openrouter/qwen",  # one upstream segment
        "openrouter/a/b/c",  # three upstream segments
        "openrouter/x-ai/grok-4~fast",  # '~' colon escape (OME-873) is an encoding, not a model
        "openrouter/qwen/qwen2.5:free",  # ':' variant can never be a url4 route
        "openrouter//model",  # empty segment
    ],
)
def test_everything_else_is_not_admissible(model_id: str) -> None:
    assert not is_dynamically_admissible(model_id)


# --- the gateway admit call (adapter) ---------------------------------------


def _admit_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://aigateway.test", transport=httpx.MockTransport(handler)
    )


@pytest.mark.asyncio
async def test_admit_model_posts_the_id_under_the_callers_identity() -> None:
    seen: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"admitted": True, "code": None, "message": None})

    source = AigatewayCatalogSource(_admit_client(upstream))
    answer = await source.admit_model(_CREDENTIAL, _TARGET)

    assert answer.outcome == "admitted"
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/models/admit"
    assert json.loads(seen[0].content) == {"model_id": _TARGET}
    assert seen[0].headers["X-User-Email"] == "alice@example.com"
    assert seen[0].headers["X-Profile"] == "default"


@pytest.mark.asyncio
async def test_a_gateway_refusal_carries_its_code_and_message() -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "admitted": False,
                "code": "model_not_on_openrouter",
                "message": "not in the catalog",
            },
        )

    source = AigatewayCatalogSource(_admit_client(upstream))
    answer = await source.admit_model(_CREDENTIAL, _TARGET)

    assert answer.outcome == "refused"
    assert answer.code == "model_not_on_openrouter"
    assert answer.message == "not in the catalog"


@pytest.mark.parametrize(
    "handler",
    [
        # An older gateway without the endpoint.
        lambda request: httpx.Response(404, json={"detail": "Not Found"}),
        # A gateway that answers something unusable.
        lambda request: httpx.Response(200, content=b"not json"),
        lambda request: httpx.Response(200, json={"weird": True}),
        # 5xx.
        lambda request: httpx.Response(503, json={}),
    ],
)
@pytest.mark.asyncio
async def test_a_gateway_that_cannot_answer_reads_as_unsupported(handler) -> None:
    source = AigatewayCatalogSource(_admit_client(handler))
    answer = await source.admit_model(_CREDENTIAL, _TARGET)
    assert answer.outcome == "unsupported"


@pytest.mark.asyncio
async def test_an_unreachable_gateway_reads_as_unsupported_not_a_crash() -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("nope")

    source = AigatewayCatalogSource(_admit_client(upstream))
    answer = await source.admit_model(_CREDENTIAL, _TARGET)
    assert answer.outcome == "unsupported"


# --- the model-parameters miss trigger --------------------------------------


class _ParamSource:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    async def fetch_model_parameters(
        self, credential: Credential, model: str
    ) -> ModelParameterResponse:
        self.fetched.append(model)
        return ModelParameterResponse(status=200, content=b"{}")


class _Admitter:
    def __init__(self, answer: AdmissionAnswer) -> None:
        self.answer = answer
        self.calls: list[str] = []

    async def admit_model(self, credential: Credential, model: str) -> AdmissionAnswer:
        self.calls.append(model)
        return self.answer


def _source(
    answer: AdmissionAnswer | None,
    admitted: AdmittedModels,
    invalidations: list[bool],
) -> tuple[ExecutableModelParameterSource, _ParamSource, _Admitter | None]:
    params = _ParamSource()
    admitter = None if answer is None else _Admitter(answer)
    return (
        ExecutableModelParameterSource(
            params,
            frozenset({_DECLARED}),
            admitted=admitted,
            admission_source=admitter,
            on_admitted=lambda: invalidations.append(True),
        ),
        params,
        admitter,
    )


@pytest.mark.asyncio
async def test_a_granted_admission_joins_the_overlay_and_forwards_the_fetch() -> None:
    admitted, invalidations = AdmittedModels(), []
    source, params, admitter = _source(AdmissionAnswer(outcome="admitted"), admitted, invalidations)

    response = await source.fetch_model_parameters(_CREDENTIAL, _TARGET)

    assert response.status == 200
    assert _TARGET in admitted
    assert invalidations == [True]
    assert params.fetched == [_TARGET]

    # Second lookup is an overlay hit: no second admit call.
    await source.fetch_model_parameters(_CREDENTIAL, _TARGET)
    assert admitter is not None and admitter.calls == [_TARGET]


@pytest.mark.asyncio
async def test_a_refusal_returns_the_gateway_shaped_404_body() -> None:
    admitted, invalidations = AdmittedModels(), []
    source, params, _ = _source(
        AdmissionAnswer(
            outcome="refused", code="provider_not_credentialed", message="connect a key"
        ),
        admitted,
        invalidations,
    )

    response = await source.fetch_model_parameters(_CREDENTIAL, _TARGET)

    # WHY a RESPONSE and not an exception: refusals ride the same
    # caller-correctable pass-through wire aigateway's own 404s use, so the SDK
    # decodes one body shape for both.
    assert response.status == 404
    detail = json.loads(response.content)["detail"]
    assert detail["code"] == "provider_not_credentialed"
    assert detail["message"] == "connect a key"
    assert detail["model"] == _TARGET
    assert _TARGET not in admitted
    assert invalidations == []
    assert params.fetched == []


@pytest.mark.asyncio
async def test_an_unsupported_gateway_degrades_to_model_not_installed() -> None:
    admitted, invalidations = AdmittedModels(), []
    source, _, _ = _source(AdmissionAnswer(outcome="unsupported"), admitted, invalidations)

    with pytest.raises(ModelNotInstalled):
        await source.fetch_model_parameters(_CREDENTIAL, _TARGET)
    assert _TARGET not in admitted


@pytest.mark.asyncio
async def test_without_an_admission_source_behavior_is_todays() -> None:
    source = ExecutableModelParameterSource(_ParamSource(), frozenset({_DECLARED}))
    with pytest.raises(ModelNotInstalled):
        await source.fetch_model_parameters(_CREDENTIAL, _TARGET)


@pytest.mark.parametrize(
    "model_id",
    ["anthropic/claude-haiku-4-5", "openrouter/x-ai/grok-4~fast"],
)
@pytest.mark.asyncio
async def test_non_admissible_ids_never_trigger_an_admit_call(model_id: str) -> None:
    admitted, invalidations = AdmittedModels(), []
    source, _, admitter = _source(AdmissionAnswer(outcome="admitted"), admitted, invalidations)

    with pytest.raises(ModelNotInstalled):
        await source.fetch_model_parameters(_CREDENTIAL, model_id)
    assert admitter is not None and admitter.calls == []


# --- the catalog projection with the overlay --------------------------------


class _UpstreamCatalog:
    def __init__(self, ids: list[str]) -> None:
        body = {"object": "list", "data": [{"id": model_id} for model_id in ids]}
        self.catalog = ModelCatalog(body=body, etag=compute_etag(body))
        self.fetches = 0

    async def fetch(self, credential: Credential) -> ModelCatalog:
        self.fetches += 1
        return self.catalog

    def max_age_s(self, credential: Credential) -> int:
        return 60

    @property
    def counters(self) -> None:
        return None

    @property
    def entry_count(self) -> int:
        return 0

    @property
    def model_parameter_source(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def _listed_ids(catalog: ModelCatalog) -> list[object]:
    data = catalog.body["data"]
    assert isinstance(data, list)
    return [row["id"] for row in data]


@pytest.mark.asyncio
async def test_an_admitted_id_survives_the_projection_and_moves_the_etag() -> None:
    upstream = _UpstreamCatalog([_DECLARED, _TARGET])
    admitted = AdmittedModels()
    catalog = ExecutableCatalog(upstream, frozenset({_DECLARED}), admitted=admitted)

    before = await catalog.fetch(_CREDENTIAL)
    assert _listed_ids(before) == [_DECLARED]

    admitted.add(_TARGET)
    after = await catalog.fetch(_CREDENTIAL)
    assert _listed_ids(after) == [_DECLARED, _TARGET]
    assert after.etag != before.etag


def test_the_catalog_exposes_its_admitted_ids_for_run_env_injection() -> None:
    upstream = _UpstreamCatalog([_DECLARED])
    admitted = AdmittedModels()
    catalog = ExecutableCatalog(upstream, frozenset({_DECLARED}), admitted=admitted)

    assert catalog.admitted_model_ids == ()
    admitted.add(_TARGET)
    assert catalog.admitted_model_ids == (_TARGET,)


# --- cache invalidation ------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_forces_the_next_fetch_upstream() -> None:
    upstream = _UpstreamCatalog([_DECLARED])
    cached = CachedCatalog(upstream, ttl_s=1000.0)

    await cached.fetch(_CREDENTIAL)
    await cached.fetch(_CREDENTIAL)
    assert upstream.fetches == 1

    cached.invalidate()
    await cached.fetch(_CREDENTIAL)
    assert upstream.fetches == 2


# --- the runner world reads URL4_CLOUD_EXTRA_MODELS -------------------------

_MINIMAL_TOML = """
[aigateway]
base_url = "http://aigateway.test"
default_route = "/claude-haiku-4-5"
models = ["claude-haiku-4-5"]
"""


def _world(env: dict[str, str]):
    import tomllib

    return parse_config(tomllib.loads(_MINIMAL_TOML), env, registry=EMPTY_MODEL_WORLD)


def test_extra_models_join_the_world_additively() -> None:
    section = _world({job_env.EXTRA_MODELS: json.dumps([_TARGET])}).aigateway
    assert section is not None
    assert f"/{_TARGET}" in routes_for(section.models)
    # The declared world is untouched.
    assert "/claude-haiku-4-5" in routes_for(section.models)


def test_an_extra_model_never_replaces_a_declared_spec() -> None:
    section = _world({job_env.EXTRA_MODELS: json.dumps(["claude-haiku-4-5"])}).aigateway
    assert section is not None
    specs = [model for model in section.models if model.id == "claude-haiku-4-5"]
    assert len(specs) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps("openrouter/a/b"),  # a string, not a list
        json.dumps([42]),
        json.dumps(["openrouter/qwen/qwen2.5:free"]),  # ':' can never be a route
    ],
)
def test_a_malformed_extra_models_value_fails_loud(raw: str) -> None:
    # WHY loud: this env is App-written (never caller input), so an unreadable
    # value is a bug — silently dropping it would hide the bug as a mid-run 404.
    with pytest.raises(WorldConfigError):
        _world({job_env.EXTRA_MODELS: raw})


# --- the job-env helpers -----------------------------------------------------


def test_extra_models_round_trip_through_the_env() -> None:
    env = job_env.extra_models_to_env([_TARGET, _DECLARED])
    assert set(env) == {job_env.EXTRA_MODELS}
    assert json.loads(env[job_env.EXTRA_MODELS]) == sorted([_TARGET, _DECLARED])


def test_no_extra_models_renders_nothing() -> None:
    assert job_env.extra_models_to_env([]) == {}


def test_extra_models_is_a_variable_the_runner_reads() -> None:
    # INVARIANT: WRITTEN_BY_APP is the contract test's key set — a key written
    # by the adapters but absent here reaches nothing, silently.
    assert job_env.EXTRA_MODELS in job_env.WRITTEN_BY_APP
