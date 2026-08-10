<script setup lang="ts">
import { computed } from 'vue'
import { useHighlight } from '@/composables/useHighlight'
import { useCopy } from '@/composables/useCopy'

interface Props {
  code: string
  language?: string
}

const props = withDefaults(defineProps<Props>(), {
  language: 'bash',
})

const { highlight } = useHighlight()
const { copied, copy } = useCopy()

const highlightedCode = computed(() => highlight(props.code, props.language))
const copyCode = () => copy(props.code)
</script>

<template>
  <div class="not-prose my-6 rounded-xl overflow-hidden shadow-sm">
    <!-- Terminal header -->
    <div class="flex items-center justify-between px-4 py-3 bg-zinc-900 border-b border-zinc-700">
      <div class="flex items-center gap-2">
        <div class="flex gap-1.5">
          <div class="w-3 h-3 rounded-full bg-red-500/80"></div>
          <div class="w-3 h-3 rounded-full bg-yellow-500/80"></div>
          <div class="w-3 h-3 rounded-full bg-green-500/80"></div>
        </div>
        <span class="ml-3 text-xs text-zinc-400">{{ language }}</span>
      </div>
      <button
        @click="copyCode"
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2 2v8a2 2 0 002 2z"
          />
        </svg>
        {{ copied ? 'Copied!' : 'Copy' }}
      </button>
    </div>
    <!-- Code content -->
    <div class="p-4 bg-zinc-900 font-mono text-sm overflow-x-auto">
      <pre class="text-zinc-100 whitespace-pre-wrap" v-html="highlightedCode"></pre>
    </div>
  </div>
</template>
