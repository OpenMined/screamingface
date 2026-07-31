import type { NavSection } from '@/composables/useDocNavigation'

// ScreamingFace Client sidebar (OME-666). Overview sits ungrouped above the
// labelled sections — a section with an empty title renders no group heading.
// User Guides and API Reference are added by the tickets that own their pages.
export const sfClientNavigation: NavSection[] = [
  {
    title: '',
    items: [{ title: 'Overview', path: '/sf-client' }],
  },
  {
    title: 'Get Started',
    items: [
      { title: 'Quickstart', path: '/sf-client/quickstartPage' },
      { title: 'Installation', path: '/sf-client/installation' },
    ],
  },
]
