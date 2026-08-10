<script setup lang="ts">
/**
 * An inline callout for something a reader needs *before* they trip over it.
 * The pattern is borrowed from the Syft docs, which repeat this markup per use;
 * here it is a component so the styling stays in one place.
 */
withDefaults(defineProps<{ label?: string }>(), { label: 'Note:' })
</script>

<template>
  <div class="not-prose my-6 p-4 rounded-lg bg-amber-500/10 border border-amber-500/30">
    <p class="text-sm text-foreground">
      <span class="text-amber-500 font-semibold">{{ label }}</span>
      <slot />
    </p>
  </div>
</template>
