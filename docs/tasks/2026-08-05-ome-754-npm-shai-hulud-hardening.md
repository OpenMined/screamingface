---
id: OME-754
linear_url: https://linear.app/openmined/issue/OME-754/harden-npm-installs-against-the-shai-hulud-worm-we-are-one-patch
status: backlog
type: task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-08-05
closed:
---

# OME-754 — harden npm installs against the Shai-Hulud worm

**We are NOT affected.** Verified 2026-08-05 against `main` @ `b594d6fc`. This is hardening,
not incident response.

On 2026-08-04 the `jaredwray` account was compromised and used to publish malicious releases of
the `keyv` / `cacheable` family, which then self-propagated via harvested CI tokens. A
`preinstall` script `setup.mjs` fetches a Bun runtime and runs `Math_Symbol.js`, which exfiltrates
npm tokens, GitHub PATs/OIDC tokens, AWS keys, Kubernetes secrets, Vault tokens, SSH keys and
Docker credentials. 868+ packages / 1,381 versions confirmed within hours.

## Scan result

All three npm surfaces carry the affected family; **no poisoned version is pinned**, installed
`node_modules` match the lockfiles exactly, and there is no `setup.mjs` preinstall hook or
`Math_Symbol.js` on disk. But `aigateway-ui` sits **exactly one release below** the poisoned
version on five packages — `@cacheable/memory` 2.2.0 vs 2.2.1, `@cacheable/utils` 2.5.0 vs 2.5.1,
`cacheable` 2.5.0 vs 2.5.1, `file-entry-cache` 11.1.5 vs 11.1.6, `flat-cache` 6.1.23 vs 6.1.24.

What saved us was `npm ci` in every CI lane (never `npm install`) and no open Dependabot npm PR
touching the set during the window. Luck plus one good habit — not a control.

## Proposed

`npm ci --ignore-scripts` where the build tolerates it (the payload only fires via `preinstall`),
a Dependabot cooldown so a hours-old release is not proposed immediately, and a known-bad
`package@version` check — `npm ci` pins but does not judge.

See the Linear issue for the full poisoned-version list and sources.
