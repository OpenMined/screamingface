<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { isLink, useDocNavigation, type NavEntry } from '@/composables/useDocNavigation'

// Renders one level of a navigation tree and recurses for children, so a group
// nested in a group needs no special case. `depth` drives styling only.
const props = withDefaults(defineProps<{ entries: NavEntry[]; depth?: number }>(), { depth: 0 })

const { isActive } = useDocNavigation(() => props.entries)
</script>

<template>
  <ul :class="depth === 0 ? 'space-y-6' : 'space-y-1'">
    <li v-for="entry in entries" :key="entry.title">
      <!-- A group labels its children and is never clickable. -->
      <template v-if="!isLink(entry)">
        <h3
          v-if="depth === 0"
          class="px-3 text-xs font-semibold tracking-widest text-muted-foreground/70 uppercase mb-3"
        >
          {{ entry.title }}
        </h3>
        <div v-else class="px-3 py-2 text-sm font-medium text-sidebar-foreground/60">
          {{ entry.title }}
        </div>
        <NavTree
          :entries="entry.children"
          :depth="depth + 1"
          :class="depth === 0 ? '' : 'ml-4 mt-1 border-l border-border/50 pl-2'"
        />
      </template>

      <!-- A link points at a page. -->
      <template v-else>
        <RouterLink
          :to="entry.path"
          :class="[
            'flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-all duration-200',
            isActive(entry.path)
              ? 'text-sidebar-primary bg-sidebar-accent border-l-2 border-sidebar-primary'
              : 'text-sidebar-foreground hover:text-sidebar-primary hover:bg-sidebar-accent/50',
          ]"
        >
          {{ entry.title }}
        </RouterLink>
        <NavTree
          v-if="entry.children"
          :entries="entry.children"
          :depth="depth + 1"
          class="ml-4 mt-1 border-l border-border/50 pl-2"
        />
      </template>
    </li>
  </ul>
</template>
