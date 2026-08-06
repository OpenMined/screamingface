<script setup lang="ts">
/**
 * Plain text notebook output — a repr, a printed line, a dict. Most SDK calls
 * return a value whose repr IS the output, so this is the default shape inside
 * an NbCell slot; the panels in this folder cover the richer cases.
 */
defineProps<{ text: string }>()
</script>

<template>
  <pre class="nbo">{{ text }}</pre>
</template>

<style scoped>
.nbo {
  margin: 0;
  padding: 0;
  background: none;
  border: 0;
  font-family: var(--nb-mono);
  font-size: 14px;
  line-height: 1.6;
  color: var(--nb-ink);
  /* Reprs run long — a 1400-character URL4 must wrap rather than scroll the page. */
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
