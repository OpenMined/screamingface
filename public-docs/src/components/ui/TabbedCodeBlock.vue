<script setup lang="ts">
import { computed } from 'vue'
import { Check, Copy } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useCodeLangStore } from '@/stores/codelangStore'
import { useHighlight } from '@/composables/useHighlight'
import { useCopy } from '@/composables/useCopy'

interface Tab {
  lang: string
  label: string
  code: string
}

const props = defineProps<{ tabs: Tab[] }>()

const codeLangStore = useCodeLangStore()
const { activeLang } = storeToRefs(codeLangStore)
const { highlight } = useHighlight()
const { copied, copy: copyText } = useCopy()

const activeTab = computed(() => props.tabs.find((t) => t.lang === activeLang.value) ?? null)

const highlightedCode = computed(() =>
  activeTab.value ? highlight(activeTab.value.code, activeTab.value.lang) : '',
)

const lineCount = computed(() => (activeTab.value ? activeTab.value.code.split('\n').length : 0))

function selectLang(lang: string) {
  activeLang.value = lang
}

function copy() {
  if (activeTab.value) copyText(activeTab.value.code)
}
</script>

<template>
  <div
    class="not-prose rounded-xl overflow-hidden border border-zinc-700 bg-zinc-900 font-mono text-sm mb-6 shadow-sm"
  >
    <!-- Header: language tabs + copy button -->
    <div class="flex items-center justify-between border-b border-zinc-700">
      <div class="flex">
        <button
          v-for="tab in tabs"
          :key="tab.lang"
          @click="selectLang(tab.lang)"
          :class="[
            'px-4 py-2.5 text-xs transition-colors border-b-2 -mb-px',
            activeLang === tab.lang
              ? 'text-zinc-100 border-indigo-500'
              : 'text-zinc-500 border-transparent hover:text-zinc-300',
          ]"
        >
          {{ tab.label }}
        </button>
      </div>
      <button
        @click="copy"
        :disabled="!activeTab"
        class="p-2 mr-2 rounded text-zinc-500 hover:text-zinc-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        :title="copied ? 'Copied!' : 'Copy code'"
      >
        <Check v-if="copied" class="w-4 h-4 text-green-400" />
        <Copy v-else class="w-4 h-4" />
      </button>
    </div>

    <!-- N/A state -->
    <div
      v-if="!activeTab"
      class="px-6 py-8 text-center text-zinc-600 text-xs uppercase tracking-widest"
    >
      Not available in {{ activeLang }}
    </div>

    <!-- Code with line numbers -->
    <div v-else class="flex text-sm py-4 overflow-x-auto">
      <!-- Line numbers -->
      <div
        class="select-none shrink-0 text-right text-zinc-600 text-xs leading-6 pl-4 pr-3 border-r border-zinc-700/50"
      >
        <div v-for="i in lineCount" :key="i" class="leading-6">{{ i }}</div>
      </div>
      <!-- Code -->
      <pre
        class="flex-1 m-0 pl-4! pr-6! leading-6 text-zinc-100 bg-transparent overflow-x-auto"
        v-html="highlightedCode"
      />
    </div>
  </div>
</template>
