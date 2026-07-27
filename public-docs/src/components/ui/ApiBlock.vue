<script setup lang="ts">
import { computed } from 'vue'
import { useCopy } from '@/composables/useCopy'

interface Props {
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  endpoint: string
  body?: string
}

const props = defineProps<Props>()

const { copied, copy } = useCopy()

const methodColors = {
  GET: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  POST: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  PATCH: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  PUT: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  DELETE: 'bg-red-500/20 text-red-400 border-red-500/30',
}

const methodColor = computed(() => methodColors[props.method])

const fullCode = computed(() => {
  if (props.body) {
    return `${props.method} ${props.endpoint}\nContent-Type: application/json\n\n${props.body}`
  }
  return `${props.method} ${props.endpoint}`
})

const copyCode = () => copy(fullCode.value)
</script>

<template>
  <div class="not-prose my-4 rounded-lg overflow-hidden border border-zinc-700">
    <!-- Header with method, endpoint, and copy button -->
    <div class="flex items-center justify-between px-4 py-3 bg-zinc-900 border-b border-zinc-700">
      <div class="flex items-center gap-3 overflow-x-auto">
        <span 
          :class="[
            'px-2.5 py-1 rounded text-xs font-bold border',
            methodColor
          ]"
        >
          {{ method }}
        </span>
        <code class="text-zinc-100 text-sm font-mono">{{ endpoint }}</code>
      </div>
      <button 
        @click="copyCode"
        class="flex-shrink-0 ml-4 flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
        {{ copied ? 'Copied!' : 'Copy' }}
      </button>
    </div>
    <!-- Request body if present -->
    <div v-if="body" class="p-4 bg-zinc-900 font-mono text-sm overflow-x-auto">
      <pre class="text-zinc-300">{{ body }}</pre>
    </div>
  </div>
</template>
