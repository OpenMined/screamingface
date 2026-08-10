<script setup lang="ts">
import type { Tone } from './types'

withDefaults(
  defineProps<{
    title?: string
    /** Monospace second line under the title */
    subtitle?: string
    /** Monospace status word on the right, e.g. COMPLETE */
    status?: string
    tone?: Tone
    /** Monospace meta on the right, after the status, e.g. a URL or duration */
    meta?: string
    /** 'top' draws the 4px accent bar above the header (connection panels);
     *  'none' relies on the outer border (report panels). */
    /** Tone for the meta text itself (the status word has its own tone) */
    metaTone?: Tone
    rule?: 'top' | 'none'
    bordered?: boolean
    /** Small monospace caption inside the bottom of the panel */
    caption?: string
  }>(),
  { tone: 'accent', metaTone: 'neutral', rule: 'top', bordered: false },
)
</script>

<template>
  <section class="nb" :class="{ 'nb--bordered': bordered }">
    <div v-if="rule === 'top'" class="nb__rule" />

    <header v-if="title || status || meta" class="nb__head">
      <div class="nb__id">
        <h3 class="nb__title">
          <slot name="title">{{ title }}</slot>
        </h3>
        <p v-if="subtitle" class="nb__sub">{{ subtitle }}</p>
      </div>
      <div class="nb__meta">
        <slot name="meta">
          <span v-if="status" class="nb__status" :data-tone="tone">{{ status }}</span>
          <span v-if="status && meta" class="nb__dot">·</span>
          <span v-if="meta" class="nb__metaText" :data-tone="metaTone">{{ meta }}</span>
        </slot>
      </div>
    </header>

    <div class="nb__body"><slot /></div>

    <p v-if="caption || $slots.caption" class="nb__caption">
      <slot name="caption">{{ caption }}</slot>
    </p>
  </section>
</template>

<style scoped>
.nb {
  font-family: var(--nb-sans);
  color: var(--nb-ink);
  background: var(--nb-surface);
}
.nb--bordered {
  border: 1px solid var(--nb-line);
}
.nb__rule {
  height: 4px;
  background: var(--nb-accent);
}
.nb__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 16px var(--nb-pad) 14px;
  border-bottom: 1px solid var(--nb-line);
}
.nb__id {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nb__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.nb__sub {
  margin: 0;
  font-family: var(--nb-mono);
  font-size: 13px;
  color: var(--nb-muted);
}
.nb__meta {
  font-family: var(--nb-mono);
  font-size: 13px;
  color: var(--nb-muted);
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 2px;
  white-space: nowrap;
}
.nb__status,
.nb__metaText {
  font-weight: 500;
  letter-spacing: 0.06em;
}
.nb__metaText[data-tone='neutral'] {
  font-weight: 400;
  letter-spacing: 0;
}
.nb__metaText[data-tone='accent'] {
  color: var(--nb-accent);
}
.nb__status[data-tone='accent'] {
  color: var(--nb-accent);
}
.nb__dot {
  color: var(--nb-muted);
}
.nb__status[data-tone='success'] {
  color: var(--nb-success);
}
.nb__status[data-tone='danger'] {
  color: var(--nb-danger);
}
.nb__status[data-tone='info'] {
  color: var(--nb-info);
}
.nb__body {
  display: flex;
  flex-direction: column;
}
.nb__caption {
  margin: 0;
  padding: 4px var(--nb-pad) 16px;
  font-family: var(--nb-mono);
  font-size: 12.5px;
  color: var(--nb-muted);
}
</style>
