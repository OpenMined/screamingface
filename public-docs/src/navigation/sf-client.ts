import type { NavEntry } from '@/composables/useDocNavigation'

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
        ],
      },
      { title: 'Benchmarks', path: '/sf-client/guides/benchmarks' },
      { title: 'Running an evaluation', path: '/sf-client/guides/running-an-evaluation' },
      { title: 'Reproduce & share (URL4)', path: '/sf-client/guides/reproduce-and-share' },
    ],
  },
]
