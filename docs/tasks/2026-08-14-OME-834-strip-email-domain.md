---
id: OME-834
linear_url: https://linear.app/openmined/issue/OME-834/publish-only-the-local-part-of-a-submitters-email-on-the-leaderboard
status: In Progress
type: Feature
priority: P2
labels: [scoreboard, agentic, autonomous]
created: 2026-08-14
closed:
---

# Publish only the local part of a submitter's email on the leaderboard

Irina's request, to avoid exposing submitters to bot spam. Measured first: the full addresses were
already public in the API without auth, so a portal-only change would have looked correct while
leaving every address in the JSON. The strip lives in the read DTOs instead.

Storage keeps the full address so OpenMined can still contact and audit a submitter (`OME-404`).

Two limits recorded rather than hidden: `trask@openmined.org` and `trask@gmail.com` both render
`trask`, and this is not anonymisation — `first.last@domain` is trivially reconstructed. Real
usernames are the fix; `OME-772` records that no such field exists.

Spec: `docs/spec/2026-08-14-OME-834-strip-email-domain.md`
Plan: `docs/plan/2026-08-14-OME-834-strip-email-domain.md`
Ledger: `docs/work/2026-08-14-OME-834-strip-email-domain.md`
