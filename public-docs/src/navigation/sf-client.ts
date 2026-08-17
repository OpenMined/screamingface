import type { NavEntry } from '@/composables/useDocNavigation'

// The SDK version these pages were written and verified against, shown once in the
// sidebar footer. A commit for now because screamingface is not on PyPI yet; when it
// ships this becomes { prefix: 'Version', label: '1.0.0', url: <PyPI release> } and
// nothing else changes.
export const sfClientVersion = {
  prefix: 'Based on state at commit',
  label: 'b698fcff',
  url: 'https://github.com/OpenMined/screamingface/commit/b698fcffd20d3dbe19c17a7b6654e302adeaf6ee',
}

// ScreamingFace Client sidebar. Organised on the Divio documentation system
// (https://docs.divio.com/documentation-system/): four separated modes —
// Tutorials (learn by doing) · How-to guides (solve one goal) · Reference
// (austere, complete) · Explanation (the "why", in the Learn section). A group
// labels its children and is never clickable; a link points at a page. The
// Reference groups mirror `sf`: the namespace (functions + submodules), then
// classes by role, so every public symbol has exactly one home.
export const sfClientNavigation: NavEntry[] = [
  { title: 'Overview', path: '/sf-client' },
  {
    title: 'Tutorials',
    children: [
      { title: 'Installation', path: '/sf-client/installation' },
      { title: 'Quickstart', path: '/sf-client/quickstartPage' },
    ],
  },
  {
    title: 'How-to guides',
    children: [
      { title: 'Connect a provider', path: '/sf-client/guides/connections' },
      {
        title: 'Compose a candidate',
        children: [
          { title: 'Models', path: '/sf-client/guides/models' },
          { title: 'Fusions', path: '/sf-client/guides/fusions' },
          { title: 'Pipelines', path: '/sf-client/guides/pipelines' },
        ],
      },
      { title: 'Choose a benchmark', path: '/sf-client/guides/benchmarks' },
      { title: 'Run an evaluation', path: '/sf-client/guides/running-an-evaluation' },
      { title: 'Publish to the leaderboard', path: '/sf-client/guides/leaderboards' },
      { title: 'Reproduce & share', path: '/sf-client/guides/reproduce-and-share' },
      { title: 'Manage the Client', path: '/sf-client/guides/clients' },
    ],
  },
  {
    title: 'Reference',
    children: [
      { title: 'The sf namespace', path: '/sf-client/api/modules' },
      {
        title: 'Classes',
        children: [
          { title: 'Client & session', path: '/sf-client/api/clients' },
          {
            title: 'Candidates',
            children: [
              { title: 'Recipe', path: '/sf-client/api/recipes' },
              { title: 'Model', path: '/sf-client/api/models' },
              { title: 'Fusion', path: '/sf-client/api/fusions' },
              { title: 'Pipeline', path: '/sf-client/api/pipelines' },
              { title: 'Url4', path: '/sf-client/api/url4' },
            ],
          },
          { title: 'Catalog', path: '/sf-client/api/benchmarks' },
          { title: 'Connections', path: '/sf-client/api/connections' },
          {
            title: 'Results & grading',
            children: [
              { title: 'Report', path: '/sf-client/api/reports' },
              { title: 'CandidateResult', path: '/sf-client/api/candidate-result' },
              { title: 'Usage', path: '/sf-client/api/usage' },
            ],
          },
          { title: 'Leaderboard', path: '/sf-client/api/leaderboards' },
          { title: 'Run events', path: '/sf-client/api/events' },
          { title: 'Errors & warnings', path: '/sf-client/api/errors' },
        ],
      },
    ],
  },
]
