<script setup lang="ts">
import type { NbCheckItem } from './types'

withDefaults(defineProps<{ items: NbCheckItem[]; label?: string; extra?: string }>(), {
  label: '',
  extra: '',
})
</script>

<template>
  <div class="cl">
    <div v-if="label || extra" class="cl__top">
      <span class="cl__label">{{ label }}</span>
      <span v-if="extra" class="cl__extra">{{ extra }}</span>
    </div>
    <ul class="cl__list">
      <li v-for="(it, i) in items" :key="i" class="cl__item">
        <span class="cl__mark" :data-done="it.done !== false">{{
          it.done === false ? '·' : '✓'
        }}</span>
        <span>{{ it.label }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cl {
  padding: 14px var(--nb-pad) 4px;
  border-top: 1px solid var(--nb-line);
}
.cl__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}
.cl__label,
.cl__extra {
  font-family: var(--nb-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--nb-muted);
  text-transform: uppercase;
}
.cl__list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cl__item {
  display: grid;
  grid-template-columns: 18px 1fr;
  align-items: baseline;
  font-size: 15px;
}
.cl__mark {
  color: var(--nb-soft);
}
.cl__mark[data-done='false'] {
  color: var(--nb-muted);
}
</style>
