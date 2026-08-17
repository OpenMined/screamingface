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

// ScreamingFace Client sidebar (OME-666). A group labels its children and is
// never clickable; a link points at a page. Overview is a plain top-level link,
// so it sits above the labelled groups without needing a group of its own.
// API Reference is added by the tickets that own those pages.
export const sfClientNavigation: NavEntry[] = [
  { title: 'Overview', path: '/sf-client' },
  {
    title: 'Get Started',
    children: [
      { title: 'Quickstart', path: '/sf-client/quickstartPage' },
      { title: 'Installation', path: '/sf-client/installation' },
    ],
  },
  {
    title: 'User Guides',
    children: [
      { title: 'Connections', path: '/sf-client/guides/connections' },
      {
        title: 'Compose',
        children: [
          { title: 'Models', path: '/sf-client/guides/models' },
          { title: 'Fusions', path: '/sf-client/guides/fusions' },
          { title: 'Pipelines', path: '/sf-client/guides/pipelines' },
        ],
      },
      { title: 'Benchmarks', path: '/sf-client/guides/benchmarks' },
      { title: 'Running an evaluation', path: '/sf-client/guides/running-an-evaluation' },
      { title: 'Leaderboards', path: '/sf-client/guides/leaderboards' },
      { title: 'Reproduce & share (URL4)', path: '/sf-client/guides/reproduce-and-share' },
    ],
  },
  {
    title: 'API Reference',
    children: [
      {
        title: 'Core classes',
        children: [
          { title: 'Recipes, Models, Fusions', path: '/sf-client/api/recipes' },
          { title: 'Models', path: '/sf-client/api/models' },
          { title: 'Benchmarks', path: '/sf-client/api/benchmarks' },
          { title: 'Reports', path: '/sf-client/api/reports' },
          { title: 'CandidateResult', path: '/sf-client/api/candidate-result' },
          { title: 'Usage', path: '/sf-client/api/usage' },
          { title: 'Clients', path: '/sf-client/api/clients' },
        ],
      },
    ],
  },
]
