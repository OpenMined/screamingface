import type { NavEntry } from '@/composables/useDocNavigation'

// "Learn" section sidebar. Uses the shared NavEntry model: a group labels its
// children and is never clickable; a link points at a page. Architecture is a
// plain top-level link, so it sits above the labelled Concepts group.
export const learnNavigation: NavEntry[] = [
  { title: 'Architecture', path: '/learn' },
  {
    title: 'Concepts',
    children: [
      { title: 'url4', path: '/learn/url4' },
      { title: 'ScreamingFace Engine', path: '/learn/engine' },
      { title: 'url4 SDK', path: '/learn/url4-sdk' },
      { title: 'Caching and compute', path: '/learn/caching' },
    ],
  },
]
