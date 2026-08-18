<script setup lang="ts">
// A small, local-state content-tab strip. Unlike TabbedCodeBlock (which switches
// code by language through a shared store), this holds arbitrary slot content per
// tab — prose, code, notebook cells — and each instance tracks its own selection.
// Slots are named tab-0, tab-1, … matching the labels array order.
import { ref } from 'vue'

const props = defineProps<{ labels: string[] }>()
const active = ref(0)
</script>

<template>
  <div class="sf-tabs">
    <div class="sf-tabs__bar" role="tablist">
      <button
        v-for="(label, i) in props.labels"
        :key="i"
        type="button"
        role="tab"
        :aria-selected="active === i"
        :class="['sf-tabs__tab', { 'sf-tabs__tab--active': active === i }]"
        @click="active = i"
      >
        {{ label }}
      </button>
    </div>
    <div
      v-for="(label, i) in props.labels"
      v-show="active === i"
      :key="`panel-${i}`"
      role="tabpanel"
      class="sf-tabs__panel"
    >
      <slot :name="`tab-${i}`" />
    </div>
  </div>
</template>

<style scoped>
.sf-tabs {
  margin: 1.5rem 0;
}
.sf-tabs__bar {
  display: flex;
  gap: 0.25rem;
  border-bottom: 1px solid var(--color-border);
}
.sf-tabs__tab {
  font-family: var(--font-sans);
  font-size: 0.9375rem;
  font-weight: var(--weight-medium);
  padding: 0.5rem 0.875rem;
  color: var(--color-muted-foreground);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s;
}
.sf-tabs__tab:hover {
  color: var(--color-foreground);
}
.sf-tabs__tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
.sf-tabs__panel {
  padding-top: 1.25rem;
}
</style>
