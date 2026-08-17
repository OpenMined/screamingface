---
id: OME-840
linear_url: https://linear.app/openmined/issue/OME-840/validate-the-submitters-address-on-the-write-path-instead-of-guessing
status: Backlog
type: Task
priority: P3
labels: [scoreboard, agentic, autonomous]
created: 2026-08-15
blocked_by: OME-834
closed:
---

# Validate the submitter's address on the write path instead of guessing on read

Owner decision, 2026-08-15: `submitted_by` is an **identity**, not a display name.

`OME-834` publishes only the local part of a submitter's address, using a serializer that inspects
the stored string and decides whether it looks like one. That is a read-time guess about a value
nothing constrains inbound, and it took four passes to get right — each pass closing one hole and
opening another (blank local part → padded address → spaced address → current).

The fix is to constrain the value at the door: require a well-formed address or `null` on
`POST /v1/scores`, reject anything else with a 422. Storage still keeps the full address, so
`OME-404`'s audit trail is untouched. Once the value is guaranteed address-shaped, the serializer
reduces to "everything before the last `@`" and the whole class of bug disappears.

Blocked on `OME-834` / #602 landing first — this rewrites the function that PR introduces.
