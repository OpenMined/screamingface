---
ticket: OME-737
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-737 — regroup dependabot.yml so security updates group and majors split out

## Intent

The structural fix of the `OME-733` epic. Everything before this cleared a backlog; this stops it
re-forming.

Authored in an isolated worktree branched from `origin/main` at `01c3b4c9`, per the standing
requirement that concurrent sessions never share a checkout.

## The two faults

**1 — `groups` does not apply to security updates.** `groups` defaults to
`applies-to: version-updates`. Every security fix therefore arrives ungrouped, one PR per
package. That is the entire single-package backlog this epic just cleared: #437, #435, #433,
#431, #430, #455, #422, #460, #432.

**2 — majors ride with patches.** One breaking major holds the security bumps hostage, and the
reverse: a major can slip in under cover of security patches. Both happened, in the same group:

- `OME-736`: `next`/`react` 19.2.8 security bumps sat behind an ESLint 10 crash and a TypeScript
  5→7 compiler rewrite, neither related to them.
- The same PR was *carrying* that TS 5→7 rewrite — a Go-based compiler reimplementation — into a
  routine dependency bump.

A third, structural fault is **not** fixable here and is recorded so nobody tries: Dependabot
cannot keep the two `FROM` lines of `apps/url4-cloud/Dockerfile` in step, because
`ghcr.io/astral-sh/uv` and `python` are different images and no grouping setting pairs them. That
is `OME-740`, mitigated by an `INVARIANT:` in the Dockerfile plus CI's smoke step.

## Design

Three groups per ecosystem instead of one:

```yaml
groups:
  <name>-security:
    applies-to: security-updates      # the directive whose absence caused fault 1
    patterns: ["*"]
  <name>-minor:
    applies-to: version-updates
    patterns: ["*"]
    update-types: ["minor", "patch"]
  <name>-major:
    applies-to: version-updates
    patterns: ["*"]
    update-types: ["major"]
```

The point is that a red `-major` PR can sit indefinitely without blocking anything, while
`-security` and `-minor` continue to flow and merge.

## Planned changes — `.github/dependabot.yml` only

- Three-group shape on all four `uv` blocks, the `aigateway-ui` npm block, and `github-actions`.
- **Add** `npm` → `/public-docs`. Its CI lane landed in `OME-738` (#484), so this entry now has
  something to verify what it produces — that ordering was the whole reason `OME-738` came first.
- **Add** `docker` → `/apps/aigateway`, `/apps/aigateway-ui`, `/apps/scoreboard`. Coverage was
  1 of 4 Dockerfiles.
- **Correct the stale comment.** It currently claims `apps/screamingface-studio/frontend` is
  excluded because it has no CI lane. That reasoning never worked: **security updates bypass the
  `directory:` allowlist entirely**, which is exactly how #422 came to exist. The comment must say
  what the exclusion does and does not buy.

## Deliberately NOT in this unit

`npm` → `/apps/screamingface-studio/frontend` and `cargo` → `/apps/screamingface-studio/src-tauri`.
Both depend on an unanswered owner question — is that tree alive? If it is dormant, deleting it
closes the repo's last remaining alert (`glib`, medium) and retires `OME-739` outright, making
both entries pointless. Adding them first would be building on an unmade decision.

## Test plan

No unit test; the config **is** the artifact. Verification is in three parts, and the first two
matter most because **a malformed `dependabot.yml` fails silently** — it does not error, it simply
stops producing PRs, which looks identical to "no updates available".

1. **Parse locally** — `yaml.safe_load`, then assert structurally: every `updates[]` entry has an
   ecosystem and directory; every `groups` entry declares `applies-to`; every declared directory
   exists on disk. Catches the silent-failure class before it reaches the repo.
2. **GitHub's own validation** — after push, the repo's Dependabot page must report no config
   error.
3. **Behavioural** — trigger "Check for updates" and confirm PRs arrive per `applies-to` bucket
   rather than one-per-package.

## Acceptance

- Every `groups` entry names an explicit `applies-to`.
- Every directory named in the config exists on disk.
- `/public-docs` present; both `screamingface-studio` entries absent, with the reason recorded.
- Docker coverage 4 of 4.
- No comment in the file still claims the directory allowlist keeps security updates out.

## Outcome

- **Actual files:** as planned — `.github/dependabot.yml` only, plus this ledger and its
  `docs/tasks/` mirror.

- **Gates — structural validation, run against the written file:**

  ```
  entries: 11  |  ungrouped: 0
  all directories exist on disk, each containing a manifest of its declared ecosystem
  every group declares an explicit applies-to
  MANIFEST COVERAGE: 10/12
    UNCOVERED: apps/screamingface-studio/frontend/package.json   (deferred, OME-739)
    UNCOVERED: apps/screamingface-studio/src-tauri/Cargo.toml    (deferred, OME-739)
  ```

  Coverage **6/12 → 10/12**; the only two gaps are the deliberately deferred ones. Docker went
  **1/4 → 4/4**.

  This validation matters more than usual: a malformed `dependabot.yml` **fails silently**. It
  does not error — it simply stops producing PRs, which is indistinguishable from "no updates
  available". Parsing and asserting locally catches that class before it reaches the repo, where
  it would present as suspicious quiet.

### Deviation — docker entries were grouped too, which the plan had written off

The plan stated the `OME-740` two-stage Dockerfile problem was "not fixable by any setting here".
That is **half wrong**, and the correction is now in the file.

Grouping the docker ecosystem per directory does not fix the mismatch — each image still resolves
to its own latest tag, so a group can still produce a builder on 3.13 beside a runtime on 3.14.
But it changes the failure from **invisible to visible**: #439 was a one-sided bump that *looked*
complete, whereas a grouped PR shows both `FROM` lines in one diff, and a reviewer can see the two
minors disagree.

So the docker blocks gained `-security` / `-version` groups. The real guard remains the
`INVARIANT:` in the Dockerfile plus CI's `Smoke both modes` step, and the comment in the config
says exactly that rather than overclaiming.

### The comment that had to change

The old file said `apps/screamingface-studio/frontend` was excluded because "it has no CI lane, so
a dependency bump there would land with nothing to verify it". The intent was sound; the mechanism
never worked. **Security updates ignore the `directory:` allowlist entirely** — they are driven by
the dependency graph — which is precisely how #422 (next, in that very tree) came to exist.

The header now states what the allowlist does and does not buy, so nobody again assumes omitting a
directory buys silence. It buys the opposite: no routine version bumps, while security PRs arrive
anyway, unverified.

### Still deferred, deliberately

`npm` → `/apps/screamingface-studio/frontend` and `cargo` → `/apps/screamingface-studio/src-tauri`,
both pending `OME-739`. If that tree is dormant, deleting it closes the repo's last open alert
(`glib`, medium) and retires the question; adding entries first would build on an unmade decision.
The config carries a comment saying so, so the gap reads as a decision rather than an oversight.

### Late addition — `ignore` rules for the two known-unmergeable majors

Prompted by the owner asking why #482 and #480 were still open. Investigating them separated two
cases the `-major` bucket alone does not:

- **#482** (`uvicorn[standard]>=0.52.0`, `testcontainers[postgres]==4.15.0`) is **legitimate**.
  `OME-735`'s `uv lock --upgrade` moved the lockfile but never touched those two `pyproject.toml`
  constraints, so this is new work rather than redundancy. CI green — merged, not closed.
- **#480** re-proposes exactly `eslint ^9→^10` and `typescript ^5→^7`, the two majors held in
  `OME-736`. It is **permanently unmergeable**, and it appeared within minutes of the holds
  landing. CI confirms: `test` and `Build the app` both FAILURE.

The `-major` group was designed so a red major can sit harmlessly rather than block security
patches. That holds for a major which might *one day* go green. It does **not** hold for one that
can never go green while its blocker exists — that regenerates weekly and is noise, and noise is
what trains people to stop reading Dependabot PRs.

So the `aigateway-ui` npm block gained `ignore` entries for `typescript >=6` and `eslint >=10`,
each commented with its blocking ticket. Removing an entry is the trigger to retry the upgrade.

This is a genuine gap in the original design of this unit, surfaced by the owner's question rather
than by my own review.
