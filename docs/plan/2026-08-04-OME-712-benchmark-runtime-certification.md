---
title: Decompose and certify the OME-712 benchmark runtime branch
ticket: OME-712
status: proposed
date: 2026-08-04
---

# Decompose and certify the OME-712 benchmark runtime branch

## Fixed inputs

- PR head: `b2c64433c34e12982dfbdcd19ac2664dc975f846`
- PR merge base: `e39f9fbaec4827fe41a3bb9bd924e40b2e7eb2d2`
- Current main at certification: `563c905f8dc815df81afa753cfaf2b587c4e4f8c`
- Cumulative PR diff: 112 files, 11,669 additions, 263 deletions
- Branch drift: 36 commits ahead and 36 commits behind current `main`
- External-state constraint: no push, PR/label edit, merge, or Linear mutation during this pass

## Proposed disposition

PR #464 should remain a read-only source branch. Re-land its behavior sequentially from updated
`main`; do not re-create the current stack. Every row below is a proposed issue/PR boundary, not an
authorized Linear mutation.

Before any extraction, resolve these gates in the certification worktree or focused successor
branches:

| Gate | Required outcome |
|---|---|
| Fail-closed scoring | Empty and otherwise zero-scored evaluations end in a typed failure. Partial completion has one owner-approved Engine/SDK contract. |
| Candidate isolation | Candidate evaluation has an explicit capability set and cannot resolve Benchmark-private routes or arbitrary outbound HTTP. |
| Image availability | Every documented control-plane registry has a paired Benchmark image, and PR CI builds the Benchmark Dockerfile. |
| Reproducible image | Build tool image and dataset-preparation dependencies are pinned rather than floating outside the lock. |
| Current-main integration | Reconstruct/rebase on current `main`, resolve workflow action drift, and rerun all three stack gates. |
| Acceptance evidence | A deployed fail-closed smoke and a hand-checked scored Kubernetes result are attached. Paid execution remains separately budget-gated. |

Local worktree status: fail-closed scoring and dev ACR image parity are implemented, and the complete
url4-cloud gate is green. They remain uncommitted and have not been propagated to PR #464 or either
upper stack. The separate PR image-build gate and reproducible Dockerfile pins remain proposed work.

| Order | Proposed landing | Owner label | Source commits or head areas | Observable acceptance |
|---:|---|---|---|---|
| 1 | Resolve outer references identically in URL4 text and AST iteration paths | `url4-python-sdk` | `4f6be0e0`, `f0201a84`, `03225938`; `packages/url4/src/url4/dag/*` | Text and AST paths resolve outer bindings, preserve row-name shadowing, and pass the URL4 gate. |
| 2 | Preserve served-model provenance across URL4 telemetry | cross-cutting parent with URL4 and url4-cloud children | `6c1771f7`; `packages/url4/src/url4/observe.py`, DAG nodes, url4-cloud connector/executor | Absent provider model stays absent; an observed served model differs visibly from the requested model. |
| 3 | Add an explicit AI Gateway local migration command | `aigateway` | `9e9de0f9`; CLI, README, CLI tests | A fresh local/Docker database can run the same migration entrypoint used by Helm. |
| 4 | Publish bounded provider-owned web-search controls | `aigateway` | `aceaaac5`, `b6700c45`, `eacc980c`; shared parameters and OpenRouter adapter | Caller can enable search and only tighten excluded domains; arbitrary provider plugin envelopes remain unreachable. |
| 5 | Apply Benchmark-owned retrieval policy in Candidate calls | `url4-cloud` | `8f68cc47`, `0cbdae85`, `6d1a62c0`, `2b33381a`, `0da8edec`, `9fd72b84`, `a6f00cd9`; connector/config tests | Typed parameters reach the Gateway, policy is task-local, excluded hosts hold on every native/Tavily hop, and unsupported fields fail closed. |
| 6 | Register the exact DRACO Gateway models | `aigateway` | `dd065a18`, `2392f4e0`; OpenRouter settings/tests | Every pinned Judge/Candidate route exists and exact seed pins fail on drift. This landing must not include provider discovery. |
| 7 | Publish and execute one Engine-owned Benchmark resource | `url4-cloud` | `b25ab663`, selected `b2c64433` benchmark registry/resource/Candidate-invocation changes, ADR 0001 | One Candidate-independent resource is fetched, linked, executed on the real Runner node, bounded against recursion/call explosions, and returns the Benchmark result. |
| 8 | Implement and prove the DRACO protocol | `url4-cloud` | `10df21da`, `93ef237c`, `a963d318`, `01fbecfa`, `0adf2eb9`, `0a6dc4dd`, selected `b2c64433` DRACO modules | One Candidate call per Case, five explicit Judge calls per criterion, private weights, hand-checked Aggregation, and fail-closed incomplete scoring. |
| 9 | Package the private DRACO Runner image | `url4-cloud` | `e89d3ca9`, `b7b3865d`, `4ce11e74`; Dockerfile, Helm, dev/release workflows | Control plane remains dataset-free; benchmark image is paired to the exact base tag, follows registry overrides, and renders on supported architectures. |

Landings 7–9 remain proposals until the owner decides whether ADR 0001 supersedes the live issue's
explicit no-convergence scope. If it does not, landing 8 must be reduced to the original URL4-native
Runner acceptance, with Engine-owned resource work moved under its own parent.

## Complete source-commit classification

Every one of the 36 source commits is accounted for here. “Extract” means reconstruct accepted hunks
from current `main`; it does not mean cherry-pick the source commit.

| Disposition | Commits | Notes |
|---|---|---|
| URL4 outer-reference landing | `4f6be0e0`, `f0201a84`, `03225938` | One focused URL4 correctness PR. |
| Model-provenance parent/children | `6c1771f7` | Split URL4 event contract from url4-cloud propagation. |
| AI Gateway migration landing | `9e9de0f9` | Independent local/deployment bootstrap defect. |
| AI Gateway bounded-search landing | `aceaaac5`, `b6700c45`, `eacc980c` | Gateway-owned parameter/security contract. |
| url4-cloud retrieval-policy landing | `8f68cc47`, `0cbdae85`, `6d1a62c0`, `2b33381a`, `0da8edec`, `9fd72b84`, `a6f00cd9`, relevant `74857cab` hunks | Must include absolute-URL denial at the Candidate boundary. |
| AI Gateway DRACO model landing | `dd065a18`, `2392f4e0` | Preserve the approved seed-test exception in the PR disclosure. |
| Benchmark resource landing | `b25ab663` plus selected `b2c64433` hunks | Exclude Cases REST, methods/actions, connections, and repo vocabulary. |
| DRACO protocol landing | `10df21da`, `93ef237c`, `a963d318`, `01fbecfa`, `0adf2eb9`, `0a6dc4dd` plus selected `b2c64433` hunks | Rebuild after the fail-closed and capability-isolation contracts are approved. |
| Benchmark deployment landing | `e89d3ca9`, `b7b3865d`, `4ce11e74` | Add ACR parity, PR build coverage, and locked preparation dependencies. |
| Move/remove generic command/data path | `76c01729`, `eae68e2e`, `47c83518` | Final in-process Aggregation no longer needs this architecture. Retain only with its own consumer and issue. |
| Move to cancellation | `12216e12`, `3eaa72a8`, `49da93e2` | Existing owner `OME-315`. |
| Move to shared REST cleanup | `087e32b6` | Useful refactor, but independent of DRACO; land with the catalog that needs it. |
| Split-by-hunk consolidation | `b2c64433` | Crosses all rows, deletes same-cycle tests, and has no commit-body reference; never cherry-pick whole. |

## Move out of the OME-712 sequence

| Work | Existing/proposed owner | Reason |
|---|---|---|
| Runner cancellation and terminal-drain fixes (`12216e12`, `3eaa72a8`, `49da93e2`) | `OME-315`, url4-cloud | Correct work, but unrelated to DRACO/Benchmark architecture and already references another issue. |
| Provider connections and `/v1/providers` proxy from `b2c64433` | `OME-496` or a dedicated provider-discovery child | SDK discovery contract, not original DRACO acceptance. |
| `GET /v1/benchmarks/{id}/cases` from `b2c64433` | `OME-723` | It is explicitly annotated for that issue and reads assets on the control plane, which the documented dataset-free deployment cannot serve. |
| Generic Benchmark methods in `benchmarks/definition.py` | remove pending a separately approved variants contract | Speculative for DRACO and later architecture work rejects the `method=` surface. |
| Candidate actions and the `case: …, input: …` context envelope | `OME-727` | Future verifier behavior and an ambiguous wire encoding do not belong in the first Benchmark protocol. |
| `[commands]`/`[data]` config, merge-config surgery, and command stdin | dedicated URL4/url4-cloud issues, or remove | The final DRACO implementation no longer uses these modules; retaining them needs an independent user and acceptance case. |
| Root `CONTEXT.md` vocabulary | repo documentation issue | Repository-wide language should not arrive inside an app feature commit. |

## Proposed Linear changes for owner approval

No action in this section has been applied.

### Update existing issues

| Issue | Proposed update |
|---|---|
| `OME-712` | Keep it non-Done and mark the current implementation blocked/needs-owner until the convergence decision, Candidate capability contract, and deployed acceptance artifact exist. Correct the status note from three to five Judge passes and from a fixed 53 criteria to an average of 39.3 criteria per task. Attach this certification and identify PR #464 as source material rather than merge-ready work. |
| `OME-315` | Move the three cancellation commits out of #464 and review them as this issue's own landing. |
| `OME-496` | Move provider connections and `/v1/providers` discovery out of #464; confirm its Engine/Gateway/SDK response schema before re-landing. |
| `OME-723` | Move the Cases endpoint here and decide whether it is served from a dataset-bearing Runner/artifact service rather than the dataset-free control plane. |
| `OME-727` | Move Candidate actions and structured Case/Input binding here; replace magic prefix parsing with a versioned payload. |

### Add focused issues if no suitable issue already exists

Use one landing label, `agentic`, and the appropriate `autonomous` or `design-session` label on each
child. Any multi-stack contract gets a coordination/decision parent and one child per landing.

| Proposed issue | Landing | Suggested priority | Blocks |
|---|---|---:|---|
| Define partial Benchmark completion and Case-count semantics | coordination/decision parent | P1 | Engine runtime and SDK execution result |
| Fail closed when a Benchmark scores no Cases | `url4-cloud` | P1 | OME-712 acceptance |
| Isolate Candidate URL4 capabilities from Benchmark internals and outbound HTTP | `url4-cloud` | P1 | OME-712 acceptance |
| Publish and verify paired Benchmark images in every supported registry | `url4-cloud` | P1 | cloud deployment acceptance |
| Build the Benchmark image in pull-request CI with locked preparation dependencies | `url4-cloud` | P2 | release confidence |
| Resolve URL4 outer references consistently in text and AST paths | `url4-python-sdk` | P1 | Engine-owned Benchmark resource |
| Preserve served-model provenance end to end | parent plus URL4/url4-cloud children | P2 | auditable Benchmark results |
| Add an AI Gateway migration entrypoint | `aigateway` | P2 | reproducible local/cloud bootstrap |
| Expose bounded provider-owned web search | `aigateway` | P1 | DRACO retrieval contract |
| Enforce Benchmark retrieval policy on every Candidate I/O path | `url4-cloud` | P1 | DRACO integrity |

Do not create a new issue for work already covered by `OME-315`, `OME-496`, `OME-723`, or `OME-727`;
update and relate those instead. Do not delete or cancel any issue merely because its code moves out
of #464.

## Head-commit extraction

The final `b2c64433` commit is not cherry-pickable as one landing: it changes 76 files across the
Gateway, url4-cloud, workflows, docs, and tests, with 4,981 additions and 1,919 deletions. Extract it
by interface:

- **Benchmark interface:** `benchmarks/contract.py`, the single-protocol subset of
  `benchmarks/definition.py`, registry/resource REST wiring, and Candidate invocation.
- **DRACO implementation:** `benchmarks/draco/{definition,prompts,runtime,tasks,verdict,aggregate,
  prepare}.py` and their new tests.
- **Connections interface:** `connections/*`, `/v1/connections`, `/v1/providers`, local loopback
  wiring, and their tests; move to provider discovery.
- **Deployment:** benchmark Dockerfile, Helm docs, and workflows.
- **Unrelated repository language:** `CONTEXT.md`; move to a repo issue.

`runner/connector.py`, `runner/config.py`, `rest/routes.py`, and `url4.toml` contain multiple rows'
behavior and must be split by hunk rather than copied wholesale.

## File-level extraction map

This map covers the complete 112-file diff. A path listed as multi-owner must be split by hunk;
every other path belongs to exactly one row.

| File set | Destination |
|---|---|
| `packages/url4/src/url4/dag/{compiler,nodes}.py`, `test_iteration_scope*.py` | URL4 outer-reference landing |
| `packages/url4/src/url4/{observe.py,dag/node.py}`, `test_usage_response_model.py` | URL4 half of model provenance |
| `packages/url4/src/url4/cli/_serve.py`, `test_serve_command_stdin.py` | Generic command-stdin issue or remove from this sequence |
| AI Gateway CLI/README/dev script and `tests/unit/test_cli.py` | AI Gateway migration landing |
| AI Gateway standard parameters, provider base/plugins, OpenRouter parameters/settings, and OpenRouter web-plugin tests | AI Gateway bounded-search landing, except model-seed hunks below |
| OpenRouter seed hunks and their exact-seed tests | AI Gateway DRACO-model landing |
| `aigateway/routes/providers.py`, its `main.py` mount, and provider/health response hunks | `OME-496` provider discovery |
| `url4_cloud/benchmarks/{contract.py,definition.py,__init__.py}`, manifests REST, ADR, diagram, and focused resource tests | Engine-owned Benchmark resource landing after the convergence decision |
| `url4_cloud/benchmarks/draco/**` and `test_draco_*` | DRACO protocol landing, except build preparation in the image row |
| `Dockerfile.benchmark`, Helm files, both image workflows, and `test_runner_image_tracks_the_app_registry.py` | Benchmark deployment landing |
| `connections/**`, REST connections, catalog provider proxy, and connection/catalog tests | `OME-496` |
| `test_benchmark_cases_endpoint.py` and the Cases-route hunks in Benchmark REST | `OME-723` |
| `rest/routes.py`, cancellation hunks in Runner main, signal/drain tests | `OME-315` |
| Runner command/data config and tests, command registration, and removed merge-config behavior | Generic command/data issue or remove |
| Model params, native-search, retrieval-policy, Tavily-guard, web-loop tests and matching Runner hunks | url4-cloud retrieval-policy landing |
| `test_response_model_provenance.py` and matching executor/connector hunks | url4-cloud half of model provenance |
| `.claude/scripts/check_layering.py` | Land with the focused Benchmark boundary it enforces |
| `CONTEXT.md` | Separate repo documentation issue |

Mandatory hunk splits:

- `apps/aigateway/src/aigateway/plugins/openrouter_provider/plugin.py` mixes provider discovery,
  search translation, and model seeds.
- `apps/url4-cloud/src/url4_cloud/{app.py,local.py}` mix Benchmark and provider-connection mounts.
- `apps/url4-cloud/src/url4_cloud/runner/{config.py,connector.py,executor.py,main.py}` mix Candidate,
  retrieval, provenance, command/data, cancellation, and Benchmark installation.
- `apps/url4-cloud/url4.toml` mixes DRACO routes, model lineup, retrieval, generic command/data, and
  future action/case behavior.
- The twelve modified pre-existing tests must be assigned alongside the contract they changed; none
  should arrive in a consolidation commit.

## Deep-module reshape

The most important seam is a Candidate runtime, not another conditional inside the existing
1,393-line connector. Its small public surface should accept a linked Candidate expression, a
structured invocation, and an explicit capability set, and return a typed outcome while reusing
ports for usage, identity, cancellation, and model dispatch. Benchmark installation remains on the
orchestrating node; Candidate evaluation receives a separate restricted node.

DRACO scoring should similarly separate:

1. verdict harvesting and strict schema/Case/pass validation;
2. protocol completeness classification; and
3. deterministic rubric reduction.

That makes the fail-closed policy testable without coupling it to prose harvesting or URL4 runtime
formatting, and keeps the arithmetic reducer small enough to compare directly with the reference.

## Certification sequence for each landing

1. Branch from current `main` in a dedicated worktree and create the approved issue mirror/ledger.
2. Write the focused specification and acceptance tests before production code.
3. Reconstruct only the required hunks; do not cherry-pick cross-cutting commits.
4. Keep prior tests unchanged. If a contract truly changes, obtain owner approval and list the exact
   old test plus replacement evidence in the PR body.
5. Run the owning stack's canonical gate and any cross-stack contract fixture.
6. Open a draft PR with `Status: In Progress :star2:`, Linear link, scope, test evidence, and the
   cross-service contract where applicable.
7. Land sequentially, then branch the next dependent landing from updated `main`.

## Review delegation after the self-review blockers are fixed

Do not ask reviewers to review the current 112-file diff as one unit. Once each extraction is green,
delegate these non-overlapping packets with an explicit fixed range and acceptance contract:

| Packet | Reviewer focus | Paths/interfaces |
|---|---|---|
| A — URL4 semantics | Text/AST parity, outer-reference/shadowing behavior, command-stdin portability if retained | `packages/url4/src/url4/dag/*`, URL4 tests |
| B — Gateway | Search parameter security, model pins, migration, provider metadata contracts | `apps/aigateway/src/aigateway/*`, seeds, migrations, provider tests |
| C — Candidate boundary | Capability isolation, identity, cancellation, usage, outbound I/O | url4-cloud Candidate runtime/connector and focused adversarial tests |
| D — DRACO protocol | Dataset revision, five-pass Judge graph, verdict validation, scoring math, incomplete outcomes | `benchmarks/draco/*` and hand-calculation fixtures |
| E — Deployment | Dataset/rubric image boundary, registry parity, chart rendering, multi-arch and reproducibility | Dockerfiles, workflows, Helm chart |
| F — SDK wire contract | Resource schema, selected/attempted/scored counts, partial/failure behavior | final Engine response against stacked SDK consumer |

Each reviewer should see only its focused PR plus any already-landed dependency. Packet F is a
cross-stack contract review after the Engine result shape is frozen, not a review of the current
stacked SDK branch against a moving response.
