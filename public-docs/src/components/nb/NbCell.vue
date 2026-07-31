<script setup lang="ts">
/**
 * A notebook cell: an input code block and the output it produced, sharing one
 * execution count. The panels in this folder are notebook *output* — this is the
 * chrome that makes them read that way on a docs page.
 *
 * Geometry and colours are lifted from the kit's reference mockup
 * (`Provider Connections.dc.html`): a 6px rail, a 56px execution-count gutter,
 * then the content. Input counts are blue, output counts red.
 */
import { computed } from 'vue'
import { Check, Copy } from 'lucide-vue-next'
import { useHighlight } from '@/composables/useHighlight'
import { useCopy } from '@/composables/useCopy'

const props = withDefaults(
  defineProps<{ count?: number | string; code: string; lang?: string }>(),
  { count: 1, lang: 'python' },
)

const { highlight } = useHighlight()
const { copied, copy } = useCopy()

const highlighted = computed(() => highlight(props.code, props.lang))
</script>

<template>
  <div class="nbc">
    <!-- Input -->
    <div class="nbc__row nbc__row--in">
      <div class="nbc__rail" />
      <span class="nbc__count nbc__count--in">[{{ count }}]:</span>
      <div class="nbc__code">
        <!-- The padding lives on this wrapper, not the <pre>: DocLayout's
             `.not-prose pre { padding: 0 }` outranks a scoped rule on the pre. -->
        <div class="nbc__src">
          <pre><code v-html="highlighted" /></pre>
        </div>
        <div class="nbc__tools">
          <button
            class="nbc__copy"
            type="button"
            :aria-label="copied ? 'Copied' : 'Copy code'"
            @click="copy(code)"
          >
            <Check v-if="copied" class="nbc__icon" />
            <Copy v-else class="nbc__icon" />
          </button>
        </div>
      </div>
    </div>

    <!-- Output. Omitted when the cell produced none — an assignment or a
         configuration call is a normal output-free cell. -->
    <div v-if="$slots.default" class="nbc__row">
      <div class="nbc__rail" />
      <span class="nbc__count nbc__count--out">[{{ count }}]:</span>
      <div class="nbc__out"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.nbc {
  padding: 14px 16px 18px;
  border: 1px solid var(--nb-cell-border);
  background: var(--nb-surface);
}
.nbc__row {
  display: grid;
  grid-template-columns: 6px 56px 1fr;
  align-items: stretch;
}
.nbc__row--in {
  margin-bottom: 14px;
}
.nbc__rail {
  background: var(--nb-cell-rail);
}
.nbc__count {
  font-family: var(--nb-mono);
  font-size: 14px;
  padding-left: 12px;
}
.nbc__count--in {
  color: var(--nb-info);
  padding-top: 13px;
}
.nbc__count--out {
  color: var(--nb-danger);
  padding-top: 2px;
}
.nbc__code {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
  background: var(--nb-fill);
  border: 1px solid var(--nb-line);
}
.nbc__src {
  flex: 1;
  min-width: 0;
  padding: 14px 16px;
  overflow-x: auto;
}
.nbc__code pre {
  margin: 0;
  background: none;
  border: 0;
  font-family: var(--nb-mono);
  font-size: 14px;
  line-height: 1.6;
}

/* The shared prism theme is built for the site's dark code blocks; on this light
   cell its punctuation and operators are effectively invisible. Restate the
   tokens against the cell's own background. */
.nbc__code :deep(code) {
  color: var(--nb-syn-plain);
}
.nbc__code :deep(.token.punctuation),
.nbc__code :deep(.token.operator),
.nbc__code :deep(.token.attr-name) {
  color: var(--nb-syn-plain);
}
.nbc__code :deep(.token.keyword),
.nbc__code :deep(.token.boolean),
.nbc__code :deep(.token.builtin) {
  color: var(--nb-syn-keyword);
  font-weight: 600;
}
.nbc__code :deep(.token.function) {
  color: var(--nb-syn-function);
}
.nbc__code :deep(.token.string),
.nbc__code :deep(.token.char) {
  color: var(--nb-syn-string);
}
.nbc__code :deep(.token.number) {
  color: var(--nb-syn-number);
}
.nbc__code :deep(.token.comment) {
  color: var(--nb-syn-comment);
}
.nbc__tools {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 11px 14px;
  flex: none;
}
.nbc__copy {
  display: flex;
  padding: 0;
  border: 0;
  background: none;
  color: var(--nb-muted);
  cursor: pointer;
}
.nbc__copy:hover {
  color: var(--nb-ink);
}
.nbc__icon {
  width: 17px;
  height: 17px;
}
.nbc__out {
  min-width: 0;
}
</style>
