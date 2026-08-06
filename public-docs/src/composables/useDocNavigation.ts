import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useRoute } from 'vue-router'

// A navigation tree is built from two node kinds, distinguished by whether the
// node has a destination:
//
//   - a GROUP labels its children and is never clickable ("USER GUIDES", "Compose")
//   - a LINK points at a page, and may itself have children
//
// Depth is not fixed: a group nested in a group is the same construct as a
// top-level one, so the sidebar renders any number of levels.
export interface NavGroup {
  title: string
  children: NavEntry[]
}

export interface NavLink {
  title: string
  path: string
  children?: NavEntry[]
}

export type NavEntry = NavGroup | NavLink

/** Narrow a node to the kind that has a destination. */
export const isLink = (entry: NavEntry): entry is NavLink => 'path' in entry

/** Every link in the tree, depth-first, in sidebar order. Groups are skipped. */
function links(entries: NavEntry[]): NavLink[] {
  return entries.flatMap((entry) => [
    ...(isLink(entry) ? [entry] : []),
    ...links(entry.children ?? []),
  ])
}

// Derives everything a doc layout needs from a section's navigation tree and
// the current route: active-link state and the flattened prev/next sequence.
// Adding a page to the navigation data automatically gives it prev/next links.
export function useDocNavigation(navigation: MaybeRefOrGetter<NavEntry[]>) {
  const route = useRoute()

  const isActive = (path: string) => route.path === path

  const isActiveOrChild = (entry: NavEntry): boolean =>
    (isLink(entry) && isActive(entry.path)) ||
    (entry.children ?? []).some((child) => isActiveOrChild(child))

  // Only links are navigable, so prev/next steps over group labels.
  const flatNav = computed(() =>
    links(toValue(navigation)).map((link) => ({ title: link.title, path: link.path })),
  )

  const currentIndex = computed(() => flatNav.value.findIndex((p) => p.path === route.path))
  const prevPage = computed(() =>
    currentIndex.value > 0 ? flatNav.value[currentIndex.value - 1] : null,
  )
  const nextPage = computed(() =>
    currentIndex.value !== -1 && currentIndex.value < flatNav.value.length - 1
      ? flatNav.value[currentIndex.value + 1]
      : null,
  )

  return { isActive, isActiveOrChild, flatNav, currentIndex, prevPage, nextPage }
}
