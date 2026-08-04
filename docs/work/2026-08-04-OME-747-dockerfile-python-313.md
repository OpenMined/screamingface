---
ticket: OME-747
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-747 — aigateway + scoreboard Dockerfiles to Python 3.13, both stages, and ignore 3.14

Authored in an isolated worktree branched from `origin/main` at `5b43c319`.

## Intent

`OME-737`'s new docker coverage began working within minutes of merging and immediately opened
#489, #490 and #491 — all three repeating the #439 fault that `OME-740` closed. Closing them
alone would defer identical PRs to next week.

## What those three PRs proved

**1 — grouping cannot pair multi-stage images.** #491 was the direct experiment, and it failed:

```
-FROM python:3.13-slim-bookworm AS runtime      <- only this moved
+FROM python:3.14-slim-bookworm AS runtime
   ghcr.io/astral-sh/uv:python3.13-...           <- builder untouched
```

`OME-737` claimed grouping would at least "make the mismatch visible in one diff". **That was too
generous and is corrected here.** Dependabot does not recognise `ghcr.io/astral-sh/uv` as
version-bearing at all, so the group has exactly **one** member — there is nothing to group it
*with*. No configuration can fix this. The only guards are the `INVARIANT:` comment and a CI step
that actually runs the built image.

**2 — real drift on two apps.** Both `apps/aigateway` and `apps/scoreboard` sit on Python 3.12 in
both stages and carry **no** guard comment. Verified they share url4-cloud's exact vulnerable
shape:

| | builder | runtime | venv copied? | PATH |
|---|---|---|---|---|
| `aigateway` | `uv:python3.12` | `python:3.12` | `COPY --from=builder /app /app` | `/app/.venv/bin` |
| `scoreboard` | `uv:python3.12` | `python:3.12` | `COPY --from=builder /app /app` | `/app/.venv/bin` |

A venv is version-keyed (`lib/python<X.Y>/`, and `pyvenv.cfg` names its interpreter), so a
one-sided bump on either yields the same `ModuleNotFoundError` #439 produced.

**Worse than url4-cloud:** neither app's CI builds its image at all, so there is no
`Smoke both modes` equivalent. url4-cloud's mismatch failed loudly in CI; on these two it would
surface at **deploy**. That gap is out of scope here but flagged below.

**3 — 3.14 is untested everywhere.** Every Python matrix in the repo runs 3.12/3.13. Merging any
of those three PRs would ship an interpreter no test in this repo has exercised.

## Planned changes

- `apps/aigateway/Dockerfile` — both stages 3.12 → 3.13, plus the `INVARIANT:`/`AIDEV-NOTE:` guard
- `apps/scoreboard/Dockerfile` — same
- `.github/dependabot.yml` — `ignore: python >=3.14` on all four docker entries, each commented
  with the condition that lifts it (CI matrices covering 3.14)
- Close #489, #490, #491

`apps/aigateway-ui/Dockerfile` is deliberately untouched: it is node, and all three of its stages
already share one `${NODE_VERSION}` ARG — structurally immune, and the pattern the Python files
lack.

## Test plan

No RED test; these are base-image pins. Verification is structural and behavioural:

1. **Both stages on the same minor** in each file — asserted programmatically by parsing every
   `FROM` line rather than read by eye, since eyeballing is exactly how #439 shipped.
2. `run_gates.py aigateway` and `run_gates.py scoreboard` green — the images are not built in CI,
   so the source gates are the available signal.
3. Config still structurally valid after the `ignore` additions: every directory exists, every
   group declares `applies-to`.

⚠️ **No Docker daemon on this machine**, and neither app's CI builds its image. So unlike
`OME-740` — where CI's `Smoke both modes` gave real proof — this change has **no runtime
verification available at all**. The mitigation is that both stages move together in one edit and
an assertion enforces it, but that is a weaker guarantee and is stated plainly rather than
implied.

## Acceptance

- Every `FROM` in both files on Python 3.13; asserted, not eyeballed.
- Both files carry the guard comment.
- `python >=3.14` ignored on the docker entries, with the lifting condition recorded.
- #489/#490/#491 closed with the reason.
- Gates green for both stacks.

## Follow-up worth its own ticket

Neither `aigateway` nor `scoreboard` CI builds its Docker image, so no test exercises these
Dockerfiles at all. `url4-cloud` gained that only because `592e4a89` broke at release time and a
build job was added in response. The same argument applies to these two.

## Outcome

- **Actual files:** as planned plus one correction — `apps/aigateway/Dockerfile`,
  `apps/scoreboard/Dockerfile`, `.github/dependabot.yml`, this ledger, its `docs/tasks/` mirror.

- **Stage parity asserted, not eyeballed** — every `FROM` line parsed and its python minor
  compared, because eyeballing is exactly how #439 shipped:

  ```
  OK  apps/aigateway/Dockerfile    python minors=['3.13']  (2 FROM lines)
  OK  apps/scoreboard/Dockerfile   python minors=['3.13']  (2 FROM lines)
  OK  apps/url4-cloud/Dockerfile   python minors=['3.13']  (2 FROM lines)
  ```

- **Gates:** `run_gates.py aigateway` and `run_gates.py scoreboard` — **ALL GATES GREEN** for
  both, including the append-only check (no test touched).

- **Config:** 11 entries, zero groups missing `applies-to`, ignores now:

  | ecosystem | directory | ignore |
  |---|---|---|
  | npm | `/apps/aigateway-ui` | `typescript >=6`, `eslint >=10` |
  | docker | `/apps/url4-cloud` | `python >=3.14` |
  | docker | `/apps/aigateway` | `python >=3.14` |
  | docker | `/apps/scoreboard` | `python >=3.14` |

### Deviation — dropped a dead ignore on aigateway-ui's docker entry

The insertion pass added `python >=3.14` to all four docker entries mechanically.
`apps/aigateway-ui/Dockerfile` is a **node** image (three stages, all on one `${NODE_VERSION}`
ARG), so a python ignore there is config that can never match. Removed. Dead config is worse than
no config — it implies a constraint that is not real, and the next reader has to work out that it
means nothing.

### Correction carried into the config

`OME-737`'s docker comment claimed grouping "partly mitigates" the multi-stage failure by putting
both images in one diff. **It does not, not even partly**, and the comment now says so. Dependabot
does not treat `ghcr.io/astral-sh/uv` as version-bearing, so the group holds exactly one member.
#491 demonstrated this within minutes of that config merging. The claim is replaced rather than
softened.

### Verification gap — stated plainly

Neither app's CI builds its image, and there is no Docker daemon here, so **this change has no
runtime verification at all**. `OME-740` had CI's `Smoke both modes` as real proof; this does not.
What stands in for it: both stages move in one edit, and an assertion enforces parity. That is
weaker, and the `AIDEV-NOTE:` in each Dockerfile now says so at the site.

Follow-up worth its own ticket: neither `aigateway` nor `scoreboard` CI builds its image, so
nothing exercises these Dockerfiles. `url4-cloud` only gained that job because `592e4a89` broke at
release time.
