<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Menu, X } from 'lucide-vue-next'
import { useCodeLangStore } from '@/stores/codelangStore'
import { useDocNavigation, type NavEntry } from '@/composables/useDocNavigation'
import NavTree from './NavTree.vue'

interface Props {
  // Optional: when omitted, the page header is skipped entirely (e.g. a notebook
  // page whose NotebookViewer renders the notebook's own title as content).
  title?: string
  description?: string
  navigation: NavEntry[]
  // Which version of the documented thing these pages describe. Optional because
  // DocLayout also serves sections that have no version to claim.
  version?: { prefix: string; label: string; url: string }
}

const props = defineProps<Props>()
const route = useRoute()
const { reset: resetCodeLang } = useCodeLangStore()

// Below lg the sidebar is off-canvas. Above it this stays false and is inert,
// because the drawer classes are all lg:-overridden.
const navOpen = ref(false)

watch(
  () => route.path,
  () => {
    resetCodeLang()
    navOpen.value = false
  },
)

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') navOpen.value = false
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

// Active state and the sidebar tree belong to NavTree; this layout only needs
// the prev/next pair.
const { prevPage, nextPage } = useDocNavigation(() => props.navigation)
</script>

<template>
  <div class="flex min-h-[calc(100vh-4rem)]">
    <!-- Backdrop, drawer only -->
    <div
      v-if="navOpen"
      class="lg:hidden fixed inset-0 z-30 bg-background/80 backdrop-blur-sm"
      @click="navOpen = false"
    />

    <!-- Sidebar: one element, two layouts. Off-canvas below lg, a static
         column above it — so the drawer reuses NavTree rather than copying it. -->
    <aside
      :class="[
        'w-64 flex flex-col border-r border-border/50 bg-sidebar',
        'fixed inset-y-0 left-0 z-40 pt-16 transition-transform duration-200',
        'lg:sticky lg:inset-y-auto lg:top-16 lg:z-auto lg:h-[calc(100vh-4rem)] lg:pt-0 lg:translate-x-0',
        navOpen ? 'translate-x-0' : '-translate-x-full',
      ]"
    >
      <button
        type="button"
        class="lg:hidden self-end m-3 p-1 text-muted-foreground hover:text-foreground"
        aria-label="Close navigation"
        @click="navOpen = false"
      >
        <X class="w-5 h-5" />
      </button>

      <div class="flex-1 overflow-y-auto py-6 px-4">
        <nav>
          <NavTree :entries="navigation" />
        </nav>
      </div>

      <!-- Version footer: the nav above is flex-1, so this sits on the bottom edge. -->
      <div v-if="version" class="border-t border-border/50 px-4 py-3">
        <p class="text-xs text-muted-foreground">
          {{ version.prefix }}
          <!-- Underlined at rest: the sidebar sits outside .prose-content, so it
               inherits none of the layout's link styling. -->
          <a
            :href="version.url"
            target="_blank"
            rel="noopener"
            class="font-mono text-primary underline underline-offset-2 hover:text-accent"
            >{{ version.label }}</a
          >
        </p>
      </div>
    </aside>

    <!-- Main content -->
    <div class="flex-1 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-6 py-10">
        <button
          type="button"
          class="lg:hidden mb-8 flex items-center gap-2 px-3 py-2 text-sm rounded-md border border-border/50 text-muted-foreground hover:text-foreground hover:border-primary/40"
          @click="navOpen = true"
        >
          <Menu class="w-4 h-4" />
          Menu
        </button>

        <!-- Page header (skipped when no title/description — e.g. notebook pages) -->
        <header v-if="title || description" class="mb-12 pb-8 border-b border-border/50">
          <h1
            v-if="title"
            class="text-4xl sm:text-5xl font-normal tracking-tight text-foreground mb-4 bg-linear-to-r from-foreground via-foreground to-muted-foreground bg-clip-text"
          >
            {{ title }}
          </h1>
          <p
            v-if="description"
            class="text-lg sm:text-xl text-muted-foreground leading-relaxed max-w-3xl"
          >
            {{ description }}
          </p>
        </header>

        <!-- Content slot -->
        <div class="prose max-w-none prose-content">
          <slot />
        </div>

        <!-- Prev / Next navigation -->
        <div
          v-if="prevPage || nextPage"
          class="flex justify-between items-center mt-16 pt-8 border-t border-border/50 gap-4"
        >
          <RouterLink
            v-if="prevPage"
            :to="prevPage.path"
            class="flex items-center gap-2 px-4 py-3 rounded-lg border border-border/50 bg-card/30 hover:border-primary/40 hover:bg-card/60 transition-all group max-w-[45%]"
          >
            <span class="text-muted-foreground group-hover:text-primary transition-colors">←</span>
            <div class="text-right min-w-0">
              <div class="text-xs text-muted-foreground mb-0.5">Previous</div>
              <div
                class="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate"
              >
                {{ prevPage.title }}
              </div>
            </div>
          </RouterLink>
          <div v-else />

          <RouterLink
            v-if="nextPage"
            :to="nextPage.path"
            class="flex items-center gap-2 px-4 py-3 rounded-lg border border-border/50 bg-card/30 hover:border-primary/40 hover:bg-card/60 transition-all group max-w-[45%] ml-auto"
          >
            <div class="text-left min-w-0">
              <div class="text-xs text-muted-foreground mb-0.5">Next</div>
              <div
                class="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate"
              >
                {{ nextPage.title }}
              </div>
            </div>
            <span class="text-muted-foreground group-hover:text-primary transition-colors">→</span>
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prose-content {
  color: var(--color-foreground);
}

.prose-content :deep(h2:not(.not-prose h2)) {
  font-family: var(--font-sans);
  font-size: 1.625rem;
  font-weight: 400;
  margin-top: 3rem;
  margin-bottom: 1.25rem;
  padding-bottom: 0.625rem;
  border-bottom: 2px solid oklch(0.35 0.05 280 / 0.4);
  color: var(--color-foreground);
  letter-spacing: -0.025em;
}

.prose-content :deep(h3:not(.not-prose h3)) {
  font-family: var(--font-sans);
  font-size: 1.375rem;
  font-weight: 400;
  margin-top: 2.25rem;
  margin-bottom: 0.875rem;
  color: var(--color-foreground);
  letter-spacing: -0.02em;
}

.prose-content :deep(h4:not(.not-prose h4)) {
  font-family: var(--font-sans);
  font-size: 1.125rem;
  font-weight: 400;
  margin-top: 1.75rem;
  margin-bottom: 0.625rem;
  color: var(--color-foreground);
  letter-spacing: -0.015em;
}

.prose-content :deep(p:not(.not-prose p)) {
  color: var(--color-muted-foreground);
  line-height: 1.75;
  margin-bottom: 1rem;
}

.prose-content :deep(ul:not(.not-prose ul)) {
  list-style-type: disc;
  padding-left: 1.5rem;
  margin-bottom: 1rem;
}

.prose-content :deep(ol:not(.not-prose ol)) {
  list-style-type: decimal;
  padding-left: 1.5rem;
  margin-bottom: 1rem;
}

.prose-content :deep(li:not(.not-prose li)) {
  color: var(--color-muted-foreground);
  margin-bottom: 0.5rem;
  line-height: 1.6;
}

.prose-content :deep(li:not(.not-prose li) strong) {
  color: var(--color-foreground);
}

.prose-content :deep(code) {
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  background-color: var(--color-muted);
  color: var(--color-primary);
  font-size: 0.875rem;
  font-family: var(--font-mono);
}

.prose-content :deep(pre:not(.not-prose pre)) {
  padding: 1rem;
  border-radius: 0.75rem;
  background-color: #18181b;
  border: none;
  overflow-x: auto;
  margin-bottom: 1.5rem;
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1.6;
}

.prose-content :deep(.not-prose pre) {
  padding: 0;
  border-radius: 0;
  background-color: transparent;
  border: none;
  margin-bottom: 0;
}

.prose-content :deep(pre:not(.not-prose pre) code) {
  background-color: transparent;
  padding: 0;
  color: #e4e4e7;
  font-family: var(--font-mono);
}

.prose-content :deep(.not-prose pre code) {
  background-color: transparent;
  padding: 0;
}

.prose-content :deep(blockquote:not(.not-prose blockquote)) {
  border-left: 4px solid oklch(0.75 0.18 195 / 0.5);
  padding-left: 1rem;
  font-style: italic;
  color: var(--color-muted-foreground);
  margin: 1.5rem 0;
}

.prose-content :deep(table:not(.not-prose table)) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.5rem;
}

.prose-content :deep(th:not(.not-prose th)) {
  font-family: var(--font-sans);
  text-align: left;
  padding: 0.75rem;
  background-color: var(--color-muted);
  font-weight: 400;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-foreground);
}

.prose-content :deep(td:not(.not-prose td)) {
  padding: 0.75rem;
  border-bottom: 1px solid oklch(0.25 0.03 280 / 0.5);
  color: var(--color-muted-foreground);
}

.prose-content :deep(a:not(.not-prose a)) {
  color: var(--color-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.prose-content :deep(a:not(.not-prose a):hover) {
  color: var(--color-accent);
}

/* Reset prose link styles inside .not-prose, but preserve explicit text-color classes */
.prose-content :deep(.not-prose a:not([class*='text-'])) {
  color: inherit;
  text-decoration: none;
}

.prose-content :deep(strong:not(.not-prose strong)) {
  font-family: var(--font-sans);
  color: var(--color-foreground);
  font-weight: 500;
}
</style>
