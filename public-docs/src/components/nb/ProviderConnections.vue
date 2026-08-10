<script setup lang="ts">
import { computed } from 'vue'
import NbPanel from './NbPanel.vue'
import NbRowList from './NbRowList.vue'
import type { NbRow, NbRowForm, Tone } from './types'

export type ProviderStatus = 'connected' | 'disconnected' | 'pending' | 'error'

export interface Provider {
  id: string
  name: string
  status: ProviderStatus
  route?: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    providers: Provider[]
    title?: string
    engineUrl?: string
    engineLabel?: string
    busy?: string[]
    /** Inline connection form per provider ID, keyed by `Provider.id`. */
    forms?: Record<string, NbRowForm>
  }>(),
  {
    title: 'Provider connections',
    engineLabel: 'Engine',
    engineUrl: '',
    busy: () => [],
    forms: () => ({}),
  },
)

const emit = defineEmits<{ connect: [p: Provider]; disconnect: [p: Provider] }>()

const LABEL: Record<ProviderStatus, string> = {
  connected: 'CONNECTED',
  disconnected: 'NOT CONNECTED',
  pending: 'CONNECTING',
  error: 'ERROR',
}
const TONE: Record<ProviderStatus, Tone> = {
  connected: 'accent',
  disconnected: 'neutral',
  pending: 'neutral',
  error: 'danger',
}

const rows = computed<NbRow[]>(() =>
  props.providers.map((p) => ({
    id: p.id,
    label: p.name,
    sublabel: p.route,
    status: LABEL[p.status],
    tone: TONE[p.status],
    action: p.status === 'connected' ? 'Disconnect' : 'Connect',
    actionGhost: p.status === 'connected',
    busy: props.busy.includes(p.id),
    disabled: p.disabled,
    form: props.forms[p.id],
  })),
)

function onAction(row: NbRow) {
  const p = props.providers.find((x) => x.id === row.id)
  if (!p) return
  // Branch rather than computing the event name: a union of names does not
  // narrow against the typed emit overloads.
  if (p.status === 'connected') emit('disconnect', p)
  else emit('connect', p)
}
</script>

<template>
  <NbPanel rule="top" :title="title" :meta="engineUrl ? engineLabel + ' · ' + engineUrl : ''">
    <NbRowList :rows="rows" last-divider @action="onAction" />
    <template v-if="$slots.default" #caption><slot /></template>
  </NbPanel>
</template>
