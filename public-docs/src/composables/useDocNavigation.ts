import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useRoute } from 'vue-router'

export interface NavItem {
  title: string
  path: string
  children?: NavItem[]
}

export interface NavSection {
  title: string
  items: NavItem[]
}

// Derives everything a doc layout needs from a section's navigation tree and
// the current route: active-link state and the flattened prev/next sequence.
// Adding a page to the navigation data automatically gives it prev/next links.
export function useDocNavigation(navigation: MaybeRefOrGetter<NavSection[]>) {
  const route = useRoute()

  const isActive = (path: string) => route.path === path

  const isActiveOrChild = (item: NavItem): boolean => {
    if (isActive(item.path)) return true
    if (item.children) return item.children.some((child) => isActive(child.path))
    return false
  }

  const flatNav = computed(() => {
    const pages: { title: string; path: string }[] = []
    for (const section of toValue(navigation)) {
      for (const item of section.items) {
        pages.push({ title: item.title, path: item.path })
        if (item.children) {
          for (const child of item.children) {
            pages.push({ title: child.title, path: child.path })
          }
        }
      }
    }
    return pages
  })

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
