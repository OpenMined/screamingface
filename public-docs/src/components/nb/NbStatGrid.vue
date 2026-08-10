<script setup lang="ts">
import type { NbStat } from './types'

withDefaults(defineProps<{ stats: NbStat[]; columns?: number }>(), { columns: 4 })
</script>

<template>
  <div class="sg" :style="{ gridTemplateColumns: 'repeat(' + columns + ', 1fr)' }">
    <div v-for="s in stats" :key="s.label" class="sg__cell">
      <span class="sg__label">{{ s.label }}</span>
      <span class="sg__value">{{ s.value }}</span>
    </div>
  </div>
</template>

<style scoped>
.sg {
  display: grid;
  gap: 1px;
  background: var(--nb-line);
  margin: 0 var(--nb-pad) 18px;
  border: 1px solid var(--nb-line);
}
.sg__cell {
  background: var(--nb-fill);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sg__label {
  font-family: var(--nb-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--nb-muted);
  text-transform: uppercase;
}
.sg__value {
  font-size: 16px;
  font-weight: 600;
}
</style>
