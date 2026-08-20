---
id: OME-920
linear_url: https://linear.app/openmined/issue/OME-920/add-a-per-profile-max-concurrency-cap-in-aigateway
status: Backlog
priority: P2
labels: [aigateway, human, design-session]
created: 2026-08-20
closed:
---

# Add a per-profile max-concurrency cap in AIGateway

Add a per-profile concurrency guardrail alongside the existing per-provider cap, so one profile
can't monopolise upstream capacity — the gateway-side, tenant-aware counterpart to `OME-908`'s
engine-side fair scheduling. Today only a per-provider cap exists (`AIGW_PROVIDER_MAX_CONCURRENCY`,
`provider_slot` in `core/concurrency.py`, acquired at `routes/chat_dispatch.py:172`); there is no
per-profile/per-account limiting (greenfield).

Proposed shape mirrors the provider pattern: `AIGW_PROFILE_MAX_CONCURRENCY` (+ overrides, `<=0`
disables), `effective_profile_limit()` + `profile_slot()` + `app.state.profile_semaphores`, and
threading `account_id`/`profile_name` into `_dispatch_with_backpressure` to nest the profile slot
inside the provider slot. Profiles are keyed `{account_id}:{provider}:{name}` and selected via the
`X-Profile` header (`routes/chat.py:242`).

Design-session: choose the key scheme (per-profile vs per-(profile,provider) vs per-profile total),
the default, precedence vs the global/provider caps, and whether `X-Profile` is the right fairness
key. Full detail in the Linear issue.

Related: `OME-908` (engine-side fair scheduling; this is the gateway-side companion).
