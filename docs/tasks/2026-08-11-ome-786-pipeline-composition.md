---
id: OME-786
linear_url: https://linear.app/openmined/issue/OME-786/support-serial-pipelines-and-recursively-composed-candidates-in-the
status: In Progress
type: Feature
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-11
closed:
---

# Support serial Pipelines and recursively composed Candidates in the Python Client

Add an immutable `sf.Pipeline` Recipe for serial Candidate composition, make Models, Fusions, and
Pipelines recursively composable complete Recipes, and provide `Recipe.then(...)` as exact
immutable Pipeline shorthand. Require explicit Fusion synthesis, normalize route strings anywhere
a Recipe is accepted, preserve distinct invocation positions, remove the universal generation
parameter default, and use URL4-native structured synthesis context. The Client continues compiling
one complete URL4 expression and evaluating it through the existing Engine lifecycle.

Related work: OME-607 defines Model/Fusion values; OME-609 defines Candidate compilation and
preflight; OME-614 owns the Engine contracts; OME-408 separately tracks importing shared raw URL4.

Spec: `docs/spec/2026-08-12-OME-786-pipeline-composition.md`
Plan: `docs/plan/2026-08-12-OME-786-pipeline-composition.md`
Ledger: `docs/work/2026-08-12-OME-786-pipeline-composition.md`
