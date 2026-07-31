<script setup lang="ts">
import { computed } from 'vue'
import type { NbScoreRow } from './types'

const props = withDefaults(
  defineProps<{
    rows: NbScoreRow[]
    label?: string
    extra?: string
    /** Bars are drawn relative to this. Defaults to the largest row value. */
    max?: number
    /** Highlights the winning row with the accent bar + tag */
    highlightBest?: boolean
    /** With 'first' (default) only the first row at the max value is marked; 'all' marks ties too */
    ties?: 'first' | 'all'
    bestTag?: string
  }>(),
  { label: '', extra: '', max: 0, highlightBest: true, ties: 'first', bestTag: 'BEST' },
)

const emit = defineEmits<{ select: [row: NbScoreRow] }>()

const scale = computed(() => props.max || Math.max(...props.rows.map((r) => r.value), 1))
const bestIds = computed<string[]>(() => {
  if (!props.highlightBest || !props.rows.length) return []
  const max = Math.max(...props.rows.map((r) => r.value))
  const winners = props.rows.filter((r) => r.value === max)
  return (props.ties === 'all' ? winners : winners.slice(0, 1)).map((r) => r.id)
})
function isBest(r: NbScoreRow) {
  return bestIds.value.includes(r.id)
}

function fmt(r: NbScoreRow) {
  return r.valueLabel ?? r.value.toFixed(1) + '%'
}
function width(r: NbScoreRow) {
  return Math.max(0, Math.min(100, (r.value / scale.value) * 100)) + '%'
}
</script>

<template>
  <div class="sl">
    <div v-if="label || extra" class="sl__top">
      <span class="sl__label">{{ label }}</span>
      <span v-if="extra" class="sl__extra">{{ extra }}</span>
    </div>

    <ul class="sl__list">
      <li
        v-for="r in rows"
        :key="r.id"
        class="sl__row"
        :class="{ 'sl__row--clickable': r.selectable }"
        @click="r.selectable && emit('select', r)"
      >
        <div class="sl__id">
          <span class="sl__name">{{ r.label }}</span>
          <span v-if="r.sublabel" class="sl__sub">{{ r.sublabel }}</span>
        </div>

        <div class="sl__track">
          <div class="sl__fill" :data-best="isBest(r)" :style="{ width: width(r) }" />
        </div>

        <div v-if="r.meta || r.metaSub" class="sl__meta">
          <span>{{ r.meta }}</span>
          <span v-if="r.metaSub" class="sl__metaSub">{{ r.metaSub }}</span>
        </div>
        <span v-else />

        <div class="sl__score">
          <span class="sl__value">{{ fmt(r) }}</span>
          <span v-if="isBest(r)" class="sl__tag">{{ bestTag }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.sl {
  padding: 16px var(--nb-pad) 4px;
}
.sl__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}
.sl__label,
.sl__extra {
  font-family: var(--nb-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--nb-muted);
  text-transform: uppercase;
}
.sl__list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
}
.sl__row {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) minmax(120px, 2fr) auto 92px;
  align-items: center;
  gap: 20px;
  padding: 14px 0;
  border-bottom: 1px solid var(--nb-hairline);
}
.sl__row:last-child {
  border-bottom: none;
}
.sl__row--clickable {
  cursor: pointer;
}
.sl__row--clickable:hover {
  background: var(--nb-fill);
}
.sl__id {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sl__name {
  font-size: 15px;
  font-weight: 600;
}
.sl__sub {
  font-family: var(--nb-mono);
  font-size: 12.5px;
  color: var(--nb-muted);
}
.sl__track {
  height: 14px;
  background: var(--nb-fill);
}
.sl__fill {
  height: 100%;
  background: var(--nb-muted);
  transition: width 300ms ease;
}
.sl__fill[data-best='true'] {
  background: var(--nb-accent);
}
.sl__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  font-family: var(--nb-mono);
  font-size: 13px;
  color: var(--nb-soft);
}
.sl__metaSub {
  color: var(--nb-muted);
}
.sl__score {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.sl__value {
  font-family: var(--nb-mono);
  font-size: 17px;
}
.sl__tag {
  font-family: var(--nb-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--nb-accent);
}
</style>
