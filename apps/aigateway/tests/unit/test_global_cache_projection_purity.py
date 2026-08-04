"""OME-305 — the global cache projection is PURE, swept over the real registry.

FEATURE: one globally SHARED exact-request cache. The key is a function of the
request body and each provider's own description of what it will send. That makes
projection purity a correctness requirement rather than a style preference: any input
the projection reads but the key cannot see is an input two callers can disagree on
while sharing a key.

STORY: as a gateway maintainer I add a provider projection and these sweeps tell me,
without my writing a single provider-specific test, whether it smuggled in state,
configuration, the clock, or the environment.

INVARIANT (plan §10): no account, profile, user, auth mode or credential may reach a
globally shared key — proven structurally for every registered plugin.

WHY this is a separate module from ``test_global_cache_registry_conformance``: that
suite asks whether each provider's declared RULES are honest (can the key builder see
the paths a rule calls ``keyed``). This one asks whether the projection FUNCTION is
well-behaved. They sweep the same registry and share its scaffolding, but they fail
for unrelated reasons and are read by different people.

AIDEV-NOTE: most registered providers do not implement the port and bypass on their
first line, which satisfies every purity sweep trivially.
``test_the_purity_sweeps_have_a_subject_that_actually_projects`` is what keeps this
file from going quietly vacuous — do not delete it.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from aigateway.core.cache_ports import CacheBypass

from ._global_cache_registry_sweep import (
    MODELS,
    REGISTRY,
    body,
    models_of,
    operator_gate_overrides,
)


def test_the_purity_sweeps_have_a_subject_that_actually_projects() -> None:
    """Anti-vacuity for every purity test below — and a liveness check on the feature.

    Most registered providers do not implement the port yet, and their projections
    return ``CacheBypass`` on the first line. Every purity sweep is therefore trivially
    satisfied by them: a hook that returns immediately reads no clock and carries no
    state. If the providers that DO project ever regressed to bypassing, the whole
    purity suite would stay green while the global cache quietly served nobody.

    So this pins two separate preconditions:
    - at least one provider produces a real projection (the purity sweeps have teeth);
    - at least one provider declares two or more models (the interleaved-state sweep
      below is not skipped for every provider by its own ``continue``).
    """
    projecting = {
        plugin.custom_llm_provider
        for plugin, model in MODELS
        if not isinstance(plugin.global_cache_projection(body(model)), CacheBypass)
    }
    assert projecting, "no registered provider projects; every purity sweep is vacuous"

    multi_model = {
        plugin.custom_llm_provider for plugin in REGISTRY.all() if len(models_of(plugin)) >= 2
    }
    assert multi_model, "no provider has two models; the interleaved sweep never runs"


def test_no_projection_carries_state_from_one_request_to_the_next() -> None:
    """Interleaved A, B, A — what plain repetition cannot catch.

    ``test_every_projection_is_deterministic_and_leaves_the_body_untouched`` calls the
    same body twice in a row, which a projection that memoized its LAST answer would
    pass perfectly. Interleaving a different model between the two calls is what makes
    such a cache visible: the second A must still equal the first A.

    INVARIANT: the projection is a function of its argument alone. Cross-request state
    is the one purity break that matters most here — a globally shared key computed
    from the previous caller's request would serve one caller another's response.
    """
    for plugin in REGISTRY.all():
        models = models_of(plugin)
        if len(models) < 2:
            continue  # a single-model provider cannot express order dependence here
        first_pass = {model: plugin.global_cache_projection(body(model)) for model in models}
        # Reverse order so neither the sequence nor an adjacent-pair effect survives.
        second_pass = {
            model: plugin.global_cache_projection(body(model)) for model in reversed(models)
        }
        assert first_pass == second_pass, plugin.custom_llm_provider


def test_no_projection_depends_on_which_instance_of_the_plugin_answers() -> None:
    """A second, identically-configured instance must project identically.

    WHY this is not covered by the signature check: ``["self", "body"]`` proves no
    identity is PASSED in, and says nothing about what the projection reads off
    ``self``. Mutable instance state — a lazily built table, a cached client, a
    per-instance id — would leave every single-process test green and then split the
    key across hosted workers, so each worker's own determinism test would pass while
    the shared cache silently partitioned.
    """
    for plugin, model in MODELS:
        overrides = operator_gate_overrides(plugin.settings_cls)
        twin = type(plugin)(plugin.settings_cls(**overrides))
        assert twin.global_cache_projection(body(model)) == plugin.global_cache_projection(
            body(model)
        ), (plugin.custom_llm_provider, model)


def test_no_projection_reads_the_clock_randomness_the_filesystem_or_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poison every ambient impurity a projection could reach for.

    WHY the pre-warm pass: a projection's FIRST call may trigger a lazy import, and an
    import legitimately reads files. Poisoning ``open`` without warming would fail on
    that import rather than on impurity, so every projection is called once before the
    poison is installed — after which any remaining I/O is genuinely per-request.

    AIDEV-NOTE: ``datetime.datetime.now`` is deliberately absent — it is a C-level
    attribute that cannot be monkeypatched. ``time`` is the reachable clock and the one
    an impure implementation would realistically use; a ``datetime``-based impurity
    would be caught instead by the determinism and twin-instance sweeps above, since
    two calls would differ.
    """
    import builtins
    import os
    import random
    import time

    for plugin, model in MODELS:
        plugin.global_cache_projection(body(model))

    def _refuse(name: str):
        def _poisoned(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(f"global_cache_projection reached {name}")

        return _poisoned

    class _PoisonedEnviron(dict[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError(f"global_cache_projection read os.environ[{key!r}]")

        def get(self, key: str, default: Any = None) -> Any:
            raise AssertionError(f"global_cache_projection read os.environ.get({key!r})")

    for module, attribute in (
        (time, "time"),
        (time, "monotonic"),
        (time, "time_ns"),
        (random, "random"),
        (random, "randint"),
        (random, "choice"),
        (builtins, "open"),
        (os, "environ"),
    ):
        if attribute == "environ":
            monkeypatch.setattr(module, attribute, _PoisonedEnviron())
        else:
            monkeypatch.setattr(module, attribute, _refuse(f"{module.__name__}.{attribute}"))

    for plugin, model in MODELS:
        plugin.global_cache_projection(body(model))


class _PoisonedSettings:
    """Any attribute read raises. Substituted for a twin plugin's ``settings``."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"global_cache_projection read settings.{name}")


def test_no_projection_reads_operator_configuration() -> None:
    """The key must not depend on per-deployment configuration.

    This is the trap the whole purity sweep exists for. A projection that consulted
    ``self.settings`` would make one deployment's key differ from another's for the
    same request while EVERY deployment's own determinism test passed — and because
    the v2 cache is SHARED, two deployments would either partition it or, worse, agree
    on a key while disagreeing on what would be dispatched.

    WHY a poison object instead of varying settings values: varying only booleans
    would sweep just one provider today (six of the seven registered settings classes
    declare no bool at all), and varying strings cannot be done generically without
    tripping a URL or enum validator. Refusing ALL attribute access is both provider-
    agnostic and total — it covers every field of every type, including ones added
    later.

    AIDEV-NOTE for whoever this test one day fails on: it is a REVIEW TRIPWIRE, not a
    claim that reading a setting is always wrong. A future provider whose dispatch
    genuinely varies with configuration has a real problem to solve — a per-deployment
    key partitions a shared cache, and folding the value into
    ``provider_adapter_revision`` (itself a settings read) only relocates it. Bring it
    to review rather than deleting this sweep; the hazard is the point.
    """
    for plugin, model in MODELS:
        twin = type(plugin)(plugin.settings_cls(**operator_gate_overrides(plugin.settings_cls)))
        expected = plugin.global_cache_projection(body(model))
        # cast: substituting a non-Settings object is the whole mechanism.
        cast(Any, twin).settings = _PoisonedSettings()
        assert twin.global_cache_projection(body(model)) == expected, (
            plugin.custom_llm_provider,
            model,
        )
