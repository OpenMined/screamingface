import type { NavEntry } from '@/composables/useDocNavigation'

// SDK sidebar. Typed like sf-client so the shared NavTree renders it.
export const sdkNavigation: NavEntry[] = [
  {
    title: 'Getting Started',
    children: [{ title: 'Overview', path: '/sdk' }],
  },
]
