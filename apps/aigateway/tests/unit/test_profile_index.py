from __future__ import annotations

from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileIndex, ProfileState


def test_profile_round_trips_through_json() -> None:
    p = Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        account_label="user@example.com",
        scopes=["user:inference"],
        last_refreshed_at=None,
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5", max_tokens=4096),
    )
    raw = p.model_dump_json()
    restored = Profile.model_validate_json(raw)
    assert restored == p


def test_profile_index_serializes_with_version() -> None:
    idx = ProfileIndex(version=1, profiles=[])
    data = idx.model_dump()
    assert data == {"version": 1, "profiles": []}
