<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ChevronDown } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useThemeStore } from '@/stores/themeStore'

const route = useRoute()
const themeStore = useThemeStore()
const { isDark } = storeToRefs(themeStore)
const { toggleTheme } = themeStore

// Top-level product/section links. Add an entry here for each documentation
// section you introduce (see src/navigation/ for the matching sidebar data).
const products = [
  { name: 'Home', path: '/' },
  { name: 'SF Client', path: '/sf-client' },
  { name: 'SDK', path: '/sdk' },
]

const currentProduct = computed(() => {
  const path = route.path
  if (path.startsWith('/sf-client')) return 'SF Client'
  if (path.startsWith('/sdk')) return 'SDK'
  return 'Home'
})

const isActive = (productPath: string) => {
  if (productPath === '/') return route.path === '/'
  return route.path.startsWith(productPath)
}

// The product link row collapses below md, so the current-product label becomes
// the only way to reach another section — it has to be a control, not text.
const productsOpen = ref(false)
watch(
  () => route.path,
  () => {
    productsOpen.value = false
  },
)

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') productsOpen.value = false
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <header class="sticky top-0 z-50 border-b border-border backdrop-blur-xl bg-background/80">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <nav class="flex items-center justify-between h-16">
        <!-- Logo -->
        <RouterLink to="/" class="flex items-center gap-3 group">
          <div
            class="w-10 h-10 flex items-center justify-center transition-all duration-300 group-hover:scale-105"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 311 360" class="w-8 h-8">
              <g clip-path="url(#clip0_navbar)">
                <path
                  d="M311.414 89.7878L155.518 179.998L-0.378906 89.7878L155.518 -0.422485L311.414 89.7878Z"
                  fill="url(#paint0_navbar)"
                />
                <path
                  d="M311.414 89.7878V270.208L155.518 360.423V179.998L311.414 89.7878Z"
                  fill="url(#paint1_navbar)"
                />
                <path
                  d="M155.518 179.998V360.423L-0.378906 270.208V89.7878L155.518 179.998Z"
                  fill="url(#paint2_navbar)"
                />
              </g>
              <defs>
                <linearGradient
                  id="paint0_navbar"
                  x1="-0.378904"
                  y1="89.7878"
                  x2="311.414"
                  y2="89.7878"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#DC7A6E" />
                  <stop offset="0.251496" stop-color="#F6A464" />
                  <stop offset="0.501247" stop-color="#FDC577" />
                  <stop offset="0.753655" stop-color="#EFC381" />
                  <stop offset="1" stop-color="#B9D599" />
                </linearGradient>
                <linearGradient
                  id="paint1_navbar"
                  x1="309.51"
                  y1="89.7878"
                  x2="155.275"
                  y2="360.285"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#BFCD94" />
                  <stop offset="0.245025" stop-color="#B2D69E" />
                  <stop offset="0.504453" stop-color="#8DCCA6" />
                  <stop offset="0.745734" stop-color="#5CB8B7" />
                  <stop offset="1" stop-color="#4CA5B8" />
                </linearGradient>
                <linearGradient
                  id="paint2_navbar"
                  x1="-0.378906"
                  y1="89.7878"
                  x2="155.761"
                  y2="360.282"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#D7686D" />
                  <stop offset="0.225" stop-color="#C64B77" />
                  <stop offset="0.485" stop-color="#A2638E" />
                  <stop offset="0.703194" stop-color="#758AA8" />
                  <stop offset="1" stop-color="#639EAF" />
                </linearGradient>
                <clipPath id="clip0_navbar">
                  <rect width="311" height="360" fill="white" />
                </clipPath>
              </defs>
            </svg>
          </div>
          <div class="flex flex-col">
            <span class="text-sm font-semibold tracking-wider text-foreground">SCREAMINGFACE</span>
            <span class="text-[10px] tracking-widest text-muted-foreground uppercase">Docs</span>
          </div>
        </RouterLink>

        <!-- Product Navigation -->
        <div class="hidden md:flex items-center gap-1">
          <RouterLink
            v-for="product in products"
            :key="product.path"
            :to="product.path"
            :class="[
              'px-3 py-2 text-sm font-normal rounded-md transition-all duration-200',
              isActive(product.path)
                ? 'text-sidebar-primary bg-sidebar-primary/10 border border-sidebar-primary/30'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            ]"
          >
            {{ product.name }}
          </RouterLink>
        </div>

        <!-- Mobile menu + actions -->
        <div class="flex items-center gap-2">
          <!-- Mobile product switcher -->
          <div class="md:hidden relative">
            <div v-if="productsOpen" class="fixed inset-0 z-40" @click="productsOpen = false" />

            <button
              type="button"
              class="relative z-50 flex items-center gap-1 px-2 py-1.5 text-sm font-normal text-sidebar-primary rounded-md hover:bg-muted/50"
              :aria-expanded="productsOpen"
              aria-haspopup="true"
              @click="productsOpen = !productsOpen"
            >
              {{ currentProduct }}
              <ChevronDown
                class="w-3.5 h-3.5 transition-transform"
                :class="productsOpen && 'rotate-180'"
              />
            </button>

            <div
              v-if="productsOpen"
              class="absolute right-0 z-50 mt-2 w-40 rounded-md border border-border bg-background shadow-lg overflow-hidden"
            >
              <RouterLink
                v-for="product in products"
                :key="product.path"
                :to="product.path"
                :class="[
                  'block px-3 py-2 text-sm',
                  isActive(product.path)
                    ? 'text-sidebar-primary bg-sidebar-primary/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
                ]"
              >
                {{ product.name }}
              </RouterLink>
              <a
                href="https://github.com/OpenMined"
                target="_blank"
                rel="noopener noreferrer"
                class="sm:hidden block px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 border-t border-border"
              >
                GitHub
              </a>
            </div>
          </div>

          <!-- Theme Toggle -->
          <button
            @click="toggleTheme"
            class="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
          >
            <!-- Sun icon (shown in dark mode) -->
            <svg
              v-if="isDark"
              class="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
              />
            </svg>
            <!-- Moon icon (shown in light mode) -->
            <svg v-else class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
              />
            </svg>
          </button>

          <!-- Roadmap link -->
          <!-- <RouterLink
            to="/roadmap"
            class="hidden sm:flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-md hover:border-sidebar-primary/50 transition-all duration-200"
          >
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            Roadmap
          </RouterLink> -->

          <!-- GitHub link -->
          <a
            href="https://github.com/OpenMined"
            target="_blank"
            rel="noopener noreferrer"
            class="hidden sm:flex items-center gap-2 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-md hover:border-sidebar-primary/50 transition-all duration-200"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path
                fill-rule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                clip-rule="evenodd"
              />
            </svg>
            GitHub
          </a>
        </div>
      </nav>
    </div>
  </header>
</template>
