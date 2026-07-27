<script setup lang="ts">
import { ref } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

interface Props {
  title: string
  defaultOpen?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  defaultOpen: false
})

const isOpen = ref(props.defaultOpen)

const toggle = () => {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <div class="not-prose my-6 border border-border rounded-lg overflow-hidden">
    <button
      @click="toggle"
      class="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors text-left"
    >
      <ChevronRight 
        :class="[
          'w-5 h-5 text-muted-foreground transition-transform',
          isOpen ? 'rotate-90' : ''
        ]"
      />
      <span class="font-semibold text-foreground">{{ title }}</span>
    </button>
    <div v-show="isOpen" class="px-4 py-4 border-t border-border prose prose-invert max-w-none">
      <slot />
    </div>
  </div>
</template>
