# aigateway-ui Guardrails

@AGENTS.md

- **BFF only.** Every call to aigateway's `/v1/admin` surface happens server-side — a server
  action or a route handler. `next.config.ts` is `output: "standalone"` and must stay that way;
  a static export has no server and cannot do this. Modules that reach aigateway carry
  `import "server-only"` so a client-component import fails the build rather than shipping the
  admin API's address to the browser.
- **The allowlist is not here.** `AIGATEWAY_ADMIN_EMAILS` lives in aigateway, which is the sole
  authority. This app never keeps a copy, never gates on an email itself, and renders whatever
  the API returns — a 403 becomes the not-an-admin page.
- **API keys are write-only.** Submitted, never rendered back, never logged, never round-tripped
  through a form's default value. aigateway returns only a masked `account_label`.
- **`X-User-Email` is read from the incoming request, never constructed.** It arrives from Envoy
  after Cloudflare Access verified it. Do not accept it as a query parameter, a cookie, or user
  input of any kind.
- **No OAuth.** Credentials in this console are static provider API keys. aigateway's OAuth
  profile/connection endpoints exist but are deliberately not surfaced here.
- **Design law is the OpenMined Design System**, vendored at `src/brand/tokens/` from
  `OpenMined/brand.openmined.org`. **Not** the `screamingface-design` skill — this is internal
  operator tooling, so it wears the parent OpenMined brand. The two systems contradict each other
  on radius, shadows, gradients, purple and type; do not mix them, and do not "correct" OMDS
  toward the ScreamingFace rules.
- **Never hardcode a color.** Literal palette values live only in `src/brand/tokens/tokens.css`;
  every other file references a token via `var(--…)`. `npm run lint:css` makes this a merge
  blocker, not a suggestion. If a color you need does not exist, add it to `tokens.css` first —
  do not reach around the gate.
- **The vendored files carry one documented divergence** (font families aliased to CSS variables
  for `next/font`). Re-syncing means re-applying it and bumping `src/brand/brand-version.txt`.
  See `src/brand/README.md`.
- **`npm ci`, never `npm install`,** in gates and CI — it installs from the lockfile and fails on
  drift. `npm install` would silently rewrite the lock and hide it.
