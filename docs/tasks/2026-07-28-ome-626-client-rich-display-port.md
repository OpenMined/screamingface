---
ticket: OME-626
status: in_progress
---

# Port the approved SDK rich display into the clean Client

Adapt the consolidated OME-626 catalogue and object-card work, including the OME-641 brand
refresh, to the v1 Client interface. Rich catalogue rendering belongs directly to
`models.list()` and `benchmarks.list()` rather than a duplicate `.view()` operation.
