<script setup lang="ts">
import type { NbRow } from './types'

withDefaults(defineProps<{ rows: NbRow[]; lastDivider?: boolean }>(), { lastDivider: false })

const emit = defineEmits<{
  action: [row: NbRow]
  choose: [row: NbRow, choice: string]
  confirm: [row: NbRow]
  cancel: [row: NbRow]
}>()

function fire(row: NbRow) {
  if (row.disabled || row.busy) return
  emit('action', row)
}

// A secret value is shown as dots — the row never renders the real characters.
function shown(form: NonNullable<NbRow['form']>) {
  return form.secret && form.value ? '•'.repeat(form.value.length) : (form.value ?? '')
}
</script>

<template>
  <ul class="rl" :class="{ 'rl--last': lastDivider }">
    <li v-for="row in rows" :key="row.id" class="rl__row">
      <div class="rl__id">
        <span class="rl__label">{{ row.label }}</span>
        <span v-if="row.sublabel" class="rl__sub">{{ row.sublabel }}</span>
      </div>

      <span v-if="row.status" class="rl__status" :data-tone="row.tone ?? 'neutral'">
        {{ row.busy ? '···' : row.status }}
      </span>

      <!-- While a connection is being set up the action button is replaced by
           the form the caller asked for. -->
      <div v-if="row.form" class="rl__form">
        <template v-if="row.form.kind === 'options'">
          <button
            v-for="choice in row.form.choices"
            :key="choice"
            type="button"
            class="rl__btn rl__btn--ghost"
            @click="emit('choose', row, choice)"
          >
            {{ choice }}
          </button>
        </template>

        <span
          v-else
          class="rl__field"
          :class="{ 'rl__field--focused': row.form.focused }"
          :data-empty="!row.form.value"
        >
          {{ shown(row.form) || row.form.placeholder }}
          <span v-if="row.form.secret" class="rl__reveal" aria-hidden="true">◠</span>
        </span>

        <button
          v-if="row.form.confirm"
          type="button"
          class="rl__btn rl__btn--solid"
          @click="emit('confirm', row)"
        >
          {{ row.form.confirm }}
        </button>
        <button
          v-if="row.form.cancel"
          type="button"
          class="rl__btn rl__btn--ghost"
          @click="emit('cancel', row)"
        >
          {{ row.form.cancel }}
        </button>
      </div>

      <button
        v-else-if="row.action"
        type="button"
        class="rl__btn"
        :class="row.actionGhost ? 'rl__btn--ghost' : 'rl__btn--solid'"
        :disabled="row.disabled || row.busy"
        @click="fire(row)"
      >
        {{ row.action }}
      </button>
      <span v-else class="rl__spacer" />
    </li>
  </ul>
</template>

<style scoped>
.rl {
  list-style: none;
  margin: 0;
  padding: 0;
}
.rl__row {
  display: grid;
  grid-template-columns: 1fr auto 156px;
  align-items: center;
  gap: 24px;
  padding: 11px var(--nb-pad);
  border-bottom: 1px solid var(--nb-line);
}
.rl:not(.rl--last) .rl__row:last-child {
  border-bottom: none;
}
.rl__id {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rl__label {
  font-size: 15px;
  font-weight: 600;
}
.rl__sub {
  font-family: var(--nb-mono);
  font-size: 12.5px;
  color: var(--nb-muted);
}
.rl__status {
  font-family: var(--nb-mono);
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--nb-muted);
  justify-self: end;
}
.rl__status[data-tone='accent'] {
  color: var(--nb-accent);
}
.rl__status[data-tone='success'] {
  color: var(--nb-success);
}
.rl__status[data-tone='danger'] {
  color: var(--nb-danger);
}
.rl__status[data-tone='info'] {
  color: var(--nb-info);
}
.rl__btn {
  font-family: var(--nb-mono);
  font-size: 14px;
  padding: 9px 16px;
  border-radius: 2px;
  cursor: pointer;
  justify-self: stretch;
  border: 1px solid var(--nb-ink);
  transition: background 120ms ease;
}
.rl__btn--solid {
  background: var(--nb-ink);
  color: var(--nb-on-accent);
}
.rl__btn--solid:hover:not(:disabled) {
  background: color-mix(in oklab, var(--nb-ink) 88%, var(--nb-surface));
}
.rl__btn--ghost {
  background: var(--nb-surface);
  color: var(--nb-ink);
}
.rl__btn--ghost:hover:not(:disabled) {
  background: var(--nb-fill);
}
.rl__btn:disabled {
  opacity: 0.45;
  cursor: default;
}
.rl__spacer {
  display: block;
}

/* The form needs more room than the 156px action column, so a row carrying one
   lets its last column size to content. */
.rl__row:has(.rl__form) {
  grid-template-columns: 1fr auto auto;
}
.rl__form {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-self: end;
}
.rl__field {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 200px;
  padding: 9px 12px;
  border: 1px solid var(--nb-line);
  background: var(--nb-surface);
  font-family: var(--nb-mono);
  font-size: 14px;
  color: var(--nb-ink);
}
.rl__field[data-empty='true'] {
  color: var(--nb-muted);
}
.rl__field--focused {
  border-color: var(--nb-info);
  box-shadow: 0 0 0 2px color-mix(in oklab, var(--nb-info) 25%, transparent);
}
.rl__reveal {
  color: var(--nb-muted);
}
</style>
