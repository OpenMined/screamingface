---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-15
finished: 2026-07-16
---

# OME-400 — Ship 00 quickstart and its SDK surface

## Intent

Create the first production ScreamingFace Python package as a coherent layer over URL4 and AI
Gateway. The public connect → pick → compose → run → compare contract uses real gateway/provider
execution by default, while explicit deterministic mock mode supports CI and committed notebook
outputs. The slice does not implement DRACO or every product-demo surface.

## Planned changes

- Add the `packages/screamingface` Python package with its own `pyproject.toml`, lockfile,
  source tree, tests, README, and examples directory.
- Add session/setup, AI Gateway HTTP client, catalog/pricing, fusion, completion ports, live and
  deterministic mock adapters, GPQA loader, provenance, run-result, and notebook-display
  modules required by `00_quickstart.ipynb`.
- Depend on `packages/url4` and compile each `Fusion` into a canonical URL4 expression that the
  public `Url4Node` facade runs through a ScreamingFace outbound I/O adapter.
- Consume AI Gateway through its existing HTTP contract without importing or changing app
  internals; temporarily map the six current providers' authentication methods inside the SDK.
- Add `packages/screamingface/examples/00_quickstart.ipynb`, committed with explicit mock-mode
  deterministic outputs and instructions for real mode.
- Register the package in the repository stack card, path-filtered CI, CODEOWNERS, Dependabot,
  and release configuration following the existing URL4 package conventions.
- Do not modify the existing user-owned URL4 notebook or lockfile changes.
- Production-hardening follow-up approved on 2026-07-16:
  - add a real `ipywidgets` setup panel backed by AI Gateway, with a static GitHub twin;
  - add public connection discovery/API-key create/replace/remove operations without retaining
    secrets;
  - make evaluation preserve successful member answers when another member fails or returns an
    invalid answer, with structured per-model failures and incomplete counts;
  - add full run provenance: profiles, token usage, per-model cost/failure details, pricing
    source/as-of date, and exact dataset identity;
  - add idempotent session close/reset and worker/client shutdown behavior;
  - replace bare hard-coded prices with immutable, dated pricing metadata and estimate labels;
  - add auth-enabled gateway and authorized gated-GPQA opt-in verification paths.
  - make local notebook execution identify a wrong Jupyter kernel with corrective instructions,
    and document how to launch/select the package environment from a repository checkout.
  - forward the interactive widget MIME bundle from `SetupPanel` so evaluating `sf.setup()` in
    Jupyter-compatible frontends renders controls instead of selecting the static HTML fallback.
  - remove SDK-local budgeting, spend confirmation, and budget UI because OME-400 requires
    `max_price` filtering but does not specify runtime budget enforcement; retain labeled pricing
    estimates and cost provenance without presenting them as gateway-enforced limits.
  - align setup with the product-demo BYOK contract: describe gateway login as unlocking the
    user's encrypted credential vault, render clean provider cards for OAuth, API-key, dual-mode,
    and keyless providers reported by AI Gateway, and support connect/replace/remove.
  - keep OME-400 isolated from AI Gateway: use a clearly marked SDK compatibility map for the six
    current provider plugins, prefer server-reported capabilities when available, and move the
    authoritative provider-capability contract to a separate gateway ticket and PR.
  - make long live evaluations observable with notebook-native per-model-call progress and timeout
    context; present providers as compact alphabetized rows with collapsed credential controls,
    no nested scrolling, emphasized authorization links, bounded automatic OAuth status polling,
    separate OAuth/API-key choices, inline save/cancel state transitions, and explicit
    disconnect/cancel actions; replace the loose login form with a compact sign-in card.
  - support safe declarative `Fusion.from_yaml(...)` recipes and `Fusion(**mapping)`, expose the
    canonical recipe explicitly as `.url4`, and render the normal Fusion value as a lineup table.
  - add an executed, generated `yaml_quickstart.ipynb` companion and drift-check both quickstarts
    in package CI.
  - make model discovery connection-independent and add one mandatory live `FusionNotReady`
    preflight before progress, dataset loading, inference calls, or spend.

- Pre-PR review fixes approved on 2026-07-16:
  - add the spec-mandated URL4 execution-seam spy test proving every panel answer traverses
    `run_url4` (a direct model loop must not satisfy the suite);
  - make a tied vote select the judge's existing valid answer per spec §7, with a deterministic
    fallback only when the judge has no valid answer, and document that fallback in the spec;
  - reconcile spec §6 wording with compose-first construction (SDK catalog at construction,
    gateway availability at the evaluation preflight);
  - add startup instructions to the notebook-path `GatewayUnavailable`, annotate `setup()` as
    returning `Session | SetupPanel`, derive run pricing provenance from the catalog entries
    actually used, and document the one-decimal rounding policy;
  - regenerate both example notebooks from their generators (staged `00_quickstart.ipynb` had
    drifted and would fail the CI drift check) and remove Jupyter `*copy*` scratch.

## Test plan

- RED: public imports and the exact OME-400 call chain do not exist before implementation.
- Contract-test gateway discovery, login, provider connections, model listing, profile selection,
  and completions against an HTTP mock transport.
- Test model/pricing filtering, input validation, judge membership, GPQA extraction/voting,
  deterministic mock evaluation, incomplete rows, score/baseline/gain arithmetic, provenance,
  and dataset boundaries.
- Test that a fusion produces a canonical, versioned URL4 expression and that evaluation invokes
  the public `Url4Node` through the SDK adapter rather than bypassing it.
- Test that provider credentials never appear in URL4 recipes or object representations.
- Test that secrets also never appear in logs, errors, or notebook output.
- Execute the notebook from a clean kernel and assert every code cell succeeds and the committed
  output contains the gain read-out.
- Run format, lint, typecheck, full tests, and coverage through the registered package gate.
- RED/GREEN contract-test widget state and callbacks through a fake gateway; static mode must make
  no auth/provider side effects and neither representation may expose credentials.
- RED/GREEN contract-test API-key connection create/replace/remove, one-shot key handling,
  ambiguous profiles, provider-readiness errors, and client/session cleanup.
- RED/GREEN test temporary capability mapping, future gateway capability override,
  OAuth/API-key provider cards, key clearing,
  authorization links, connect/replace/remove actions, and keyless-provider disclosure.
- RED/GREEN test mixed success/failure/invalid-answer panels, structured failure provenance,
  usage/cost aggregation, and exact pricing metadata.
- Keep auth-enabled and real GPQA/provider tests opt-in, minimal, and excluded from
  stable committed benchmark claims.

## Acceptance

- `import screamingface as sf` works from the package environment.
- `sf.setup()` defaults to live AI Gateway authentication; explicit mock mode is required for
  simulation and never selected silently.
- `sf.models.list(max_price=20)`, `sf.Fusion`, `Fusion.from_yaml`, `.url4`, and
  `.evaluate("gpqa", first=20, seed=0)` work in both modes through the same public surface.
- The returned run exposes numeric `score`, `baseline`, and `gain`, with
  `gain == score - baseline` at the documented precision.
- Fusion execution is URL4-backed and each panel response is reused for baseline.
- The quickstart executes offline in explicit mock mode and is committed with visibly simulated
  output; an opt-in live smoke test covers at least two gateway providers.
- Package quality gates are green without weakening URL4's existing gates.
- In a notebook, `sf.setup()` returns a production BYOK widget that explains gateway login,
  discovers provider authentication capabilities, and supports OAuth plus masked API-key
  connect/replace/remove actions; the same operations are public headless APIs in scripts.
- A member/provider failure does not discard other answers; the Run reports exact failures,
  invalid answers, usage, costs, profiles, pricing provenance, and incomplete rows.
- Replacing/resetting/closing a live Session closes its gateway client and does not leak worker
  threads or event loops.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added `packages/screamingface` with package metadata/lockfile, SDK source,
  bundled synthetic fixture, HTTP and live/mock adapters, tests, opt-in live smoke test, notebook
  generator, and executed `examples/00_quickstart.ipynb`; registered the package in SDLC,
  Dependabot, release-please, and path-filtered CI; added OME-400 spec/plan/task/work records. The
  production hardening adds an ipywidgets setup/login panel, public provider-connection APIs,
  typed partial-provider failures, detailed run/model provenance, dated pricing metadata, clean
  lifecycle/shutdown behavior, and auth-enabled/gated-GPQA opt-in tests. The final BYOK pass adds
  OAuth/API-key provider cards backed temporarily by an SDK compatibility map, without changing
  AI Gateway.
  Fusion recipes can now be loaded safely from YAML, render as lineup tables, and expose their
  canonical recipe explicitly through `.url4`. Run values now render as provenance-rich result
  cards with headline metrics and per-model accuracy bars while retaining explicit simulation/live
  labeling. The executed `yaml_quickstart.ipynb` companion covers file and inline configuration,
  exact model-ID validation, explicit URL4 access, and the full evaluate/compare path. Python and
  YAML composition now share connection-independent catalog discovery and the same aggregated,
  zero-call readiness preflight at evaluation time. Evaluation now runs through an embedded public
  `Url4Node` whose outbound adapter is the only model-call seam, and recipes carry versioned
  non-secret name/judge metadata needed for exact future import.
- **Pre-PR review round (2026-07-16):** three parallel spec-conformance reviews found the
  staged `00_quickstart.ipynb` had drifted from its generator (regenerated; SHA unchanged and
  byte-deterministic), the spec-mandated URL4 execution-seam spy test missing (added
  `tests/test_url4_seam.py` proving each question executes through an embedded public `Url4Node`
  and that a
  URL4 bypass yields no answers), and a tie-break deviation (a tied vote now selects the
  judge's existing valid answer per spec §7, with the alphabetical fallback documented in the
  spec for judgeless/invalid-judge ties). Also fixed: startup instructions on the
  notebook-path `GatewayUnavailable`, `setup()` return annotation, run pricing provenance now
  derived from the catalog entries in the fusion, a documented one-decimal rounding policy,
  and spec §6 reworded to match compose-first construction (SDK catalog at construction,
  gateway availability at preflight). Jupyter `*copy*` scratch removed and the autosaving
  notebook server stopped before staging.
- **Commits:** `feat(screamingface): ship OME-400 quickstart SDK thin slice` on
  `OME-400-ship-quickstart-sdk` (Refs: OME-400); Linear label/state sync remains an owner
  handoff.
- **Embedded-node landing round (2026-07-16):** the Url4Node refactor was validated and landed
  with a documented append-only override (`--skip-append-only` once): the seam tests retarget from
  `url4.dag.run` to the `Url4Node` facade because that seam was replaced, and the successors are
  strictly stronger (they additionally assert the rendered request equals `fusion.url4`). The
  notebook generators were tidied for shareability (value-proposition intro, embedded-node wording
  instead of the ambiguous "public URL4 node", cross-links between the two quickstarts) and both
  notebooks regenerated. The URL4 topology decision record (embedded execution; OME-466 optional,
  not a dependency) was appended to
  `docs/questions/2026-07-16-screamingface-url4-integration-questions.md`.
- **Gates:** ScreamingFace package checks are green (Ruff check/format, Pyright, 68 tests +
  three explicitly skipped-by-default live tests, 95.97% coverage); clean-kernel notebook
  execution green and byte-deterministic at SHA-256
  `b3cc031afc643f3905e3b0c2cc1312a32030c2c148ee786a90ca812cf5bb83cf`; wheel and sdist build
  green with the widget and bundled fixture verified. The YAML companion is clean-kernel green and
  byte-deterministic at SHA-256
  `0336a9d15980f7820e97d05489c8b68be846b7d8dd4711907092ac0114a09b6b`. The new
  auth-enabled proof passed against a
  fresh local AI Gateway using `sf.setup(username=..., password=...)`; its server was stopped and
  disposable database deleted afterward. The opt-in live smoke previously passed against local AI
  Gateway with active Anthropic and Codex OAuth connections. A final real run returned score 100,
  baseline 100, gain 0, incomplete 0, and estimated cost $0.001554. The gated
  GPQA loader proof passed using the machine's existing Hugging Face CLI login after dataset access
  was accepted; it loaded one row while asserting only ID/shape, and no gated question text was
  printed, rendered, or committed. URL4's 704-test suite is green at 97.06% coverage and its
  package source is unchanged by OME-400. AI Gateway's full gate is green (Ruff check/format,
  Pyright, enterprise-import boundary, 732 tests + 28 skips, 89.00% coverage) and its source is
  unchanged by OME-400. Browser-level
  visual inspection was unavailable in this session, so widget appearance remains a manual
  handoff check; Jupyter MIME rendering and all card interactions are covered by automated tests.
- **Deviations:** live verification found and fixed persistent async-client event-loop reuse and a
  one-second completion timeout inherited from health checks. SDK-local budgeting was removed
  after scope review established that only `max_price` filtering belongs to OME-400. Gemini OAuth
  became active but its upstream Code Assist account lacked a
  `cloudaicompanionProject`, so the passing two-provider proof used Anthropic and Codex. AI Gateway
  authentication/connection infrastructure is complete; the existing brand-demo
  `01_authentication.ipynb` is a simulated UX specification, not a missing gateway dependency.
  Linear MCP was unavailable, so exact priority/created metadata, `pkg/screamingface-sdk` label
  creation/UUID registration, comment, and state transition remain owner handoff items.
