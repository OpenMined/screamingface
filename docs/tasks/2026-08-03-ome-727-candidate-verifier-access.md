---
ticket: OME-727
linear_url: https://linear.app/openmined/issue/OME-727/give-candidate-blobs-verifier-access-case-slot-ifeval-action-routes
status: done
type: feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-03
closed:
---

# Bind the case id into candidate blobs and expose check/select/finalize actions so candidate-side verifier loops self-check without seeing instruction ids

`$case` bound into candidate scope (optional second slot); ifeval action routes
(check-feedback / select / finalize) advertised via additive manifest `actions` map.
Enables candidate-side verifier loops with the exam frozen. Parent `OME-718`;
engine half of the CorrectiveEnsemble pair (`OME-728`).
