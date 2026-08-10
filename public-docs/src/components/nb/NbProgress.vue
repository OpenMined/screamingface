<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ label?: string; value: number; total: number; indeterminate?: boolean }>(),
  { label: '', indeterminate: false },
)

const pct = computed(() =>
  props.total > 0 ? Math.min(100, Math.round((props.value / props.total) * 100)) : 0,
)
</script>

<template>
  <div class="pg">
    <div class="pg__top">
      <span class="pg__label">{{ label }}</span>
      <span class="pg__count">{{ value }}/{{ total }}</span>
    </div>
    <div class="pg__track" role="progressbar" :aria-valuenow="value" :aria-valuemax="total">
      <div
        class="pg__fill"
        :class="{ 'pg__fill--pulse': indeterminate }"
        :style="{ width: pct + '%' }"
      />
    </div>
  </div>
</template>

<style scoped>
.pg {
  padding: 14px var(--nb-pad) 16px;
}
.pg__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}
.pg__label {
  font-size: 15px;
  color: var(--nb-soft);
}
.pg__count {
  font-family: var(--nb-mono);
  font-size: 13px;
  color: var(--nb-muted);
}
.pg__track {
  margin-top: 12px;
  height: 5px;
  background: var(--nb-line);
}
.pg__fill {
  height: 100%;
  background: var(--nb-accent);
  transition: width 300ms ease;
}
.pg__fill--pulse {
  animation: pgPulse 1.2s ease-in-out infinite;
}
@keyframes pgPulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}
</style>
