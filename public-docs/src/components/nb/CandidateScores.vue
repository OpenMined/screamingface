<script setup lang="ts">
import { computed } from 'vue'
import NbPanel from './NbPanel.vue'
import NbScoreList from './NbScoreList.vue'
import type { NbScoreRow } from './types'

export interface Candidate {
  id: string
  name: string
  /** Score as a percentage, 0-100 */
  score: number
  casesScored: number
  casesTotal: number
  /** 0-100 */
  coverage?: number
}

const props = withDefaults(
  defineProps<{
    candidates: Candidate[]
    title?: string
    benchmark?: string
    caseLabel?: string
    complete?: boolean
    sectionLabel?: string
    /** Cap rendered rows; the remainder is summarised as "+N MORE" */
    limit?: number
  }>(),
  {
    title: 'Candidate study',
    benchmark: '',
    caseLabel: '',
    complete: true,
    sectionLabel: 'Candidate scores',
    limit: 0,
  },
)

const emit = defineEmits<{ select: [c: Candidate] }>()

const shown = computed(() =>
  props.limit ? props.candidates.slice(0, props.limit) : props.candidates,
)

const rows = computed<NbScoreRow[]>(() =>
  shown.value.map((c) => ({
    id: c.id,
    label: c.name,
    sublabel: c.casesScored + '/' + c.casesTotal + ' cases',
    value: c.score,
    meta: (c.coverage ?? 100) + '%',
    metaSub: 'coverage',
    selectable: true,
  })),
)

const subtitle = computed(() => [props.benchmark, props.caseLabel].filter(Boolean).join(' · '))
const scored = computed(() => props.candidates.filter((c) => c.casesScored >= c.casesTotal).length)
const headerMeta = computed(() => `${scored.value}/${props.candidates.length} CANDIDATES SCORED`)
const hidden = computed(() => props.candidates.length - shown.value.length)

function onSelect(row: NbScoreRow) {
  const c = props.candidates.find((x) => x.id === row.id)
  if (c) emit('select', c)
}
</script>

<template>
  <NbPanel
    bordered
    rule="none"
    :title="title"
    :subtitle="subtitle"
    :status="complete ? 'COMPLETE' : 'RUNNING'"
    :tone="complete ? 'accent' : 'info'"
    :meta="headerMeta"
    meta-tone="accent"
  >
    <NbScoreList
      :rows="rows"
      :label="sectionLabel"
      :extra="hidden > 0 ? `+${hidden} MORE` : ''"
      @select="onSelect"
    />
  </NbPanel>
</template>
