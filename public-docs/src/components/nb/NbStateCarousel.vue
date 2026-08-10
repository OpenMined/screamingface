<script setup lang="ts" generic="T extends { caption?: string }">
/**
 * Steps through a sequence of component states, one at a time, with a caption
 * and dot navigation. Unlike ImageCarousel this slides *rendered components*
 * rather than images, so a walkthrough follows the theme and stays in sync with
 * the components it demonstrates.
 *
 * Auto-advance is deliberately off: these are read-at-your-own-pace steps, not
 * a marquee.
 */
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useCarousel } from '@/composables/useCarousel'

const props = withDefaults(defineProps<{ steps: T[]; label?: string }>(), { label: '' })

const { currentIndex, next, prev, goTo } = useCarousel(() => props.steps.length)

const current = computed(() => props.steps[currentIndex.value])
const position = computed(() => `${currentIndex.value + 1} / ${props.steps.length}`)
</script>

<template>
  <div class="sc">
    <div class="sc__bar">
      <span class="sc__label">{{ label }}</span>
      <div class="sc__nav">
        <span class="sc__pos">{{ position }}</span>
        <button
          type="button"
          class="sc__arrow"
          aria-label="Previous step"
          :disabled="currentIndex === 0"
          @click="prev"
        >
          <ChevronLeft class="sc__icon" />
        </button>
        <button
          type="button"
          class="sc__arrow"
          aria-label="Next step"
          :disabled="currentIndex === steps.length - 1"
          @click="next"
        >
          <ChevronRight class="sc__icon" />
        </button>
      </div>
    </div>

    <!-- Guarded so the slot binding is a definite T, not T | undefined. -->
    <div v-if="current" class="sc__stage">
      <slot :step="current" :index="currentIndex" />
    </div>

    <p v-if="current?.caption" class="sc__caption">{{ current.caption }}</p>

    <div class="sc__dots">
      <button
        v-for="(step, i) in steps"
        :key="i"
        type="button"
        class="sc__dot"
        :class="{ 'sc__dot--on': i === currentIndex }"
        :aria-label="`Step ${i + 1}`"
        :aria-current="i === currentIndex"
        @click="goTo(i)"
      />
    </div>
  </div>
</template>

<style scoped>
.sc {
  border: 1px solid var(--nb-line);
  background: var(--nb-surface);
}
.sc__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px var(--nb-pad);
  border-bottom: 1px solid var(--nb-line);
}
.sc__label,
.sc__pos {
  font-family: var(--nb-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--nb-muted);
}
.sc__nav {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sc__arrow {
  display: flex;
  padding: 4px;
  border: 1px solid var(--nb-line);
  background: var(--nb-surface);
  color: var(--nb-ink);
  cursor: pointer;
}
.sc__arrow:hover:not(:disabled) {
  border-color: var(--nb-ink);
}
.sc__arrow:disabled {
  opacity: 0.35;
  cursor: default;
}
.sc__icon {
  width: 15px;
  height: 15px;
}
.sc__stage {
  padding: var(--nb-pad);
}
.sc__caption {
  margin: 0;
  padding: 0 var(--nb-pad) 14px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--nb-muted);
}
.sc__dots {
  display: flex;
  gap: 6px;
  padding: 0 var(--nb-pad) 16px;
}
.sc__dot {
  width: 22px;
  height: 3px;
  border: 0;
  padding: 0;
  background: var(--nb-line);
  cursor: pointer;
}
.sc__dot--on {
  background: var(--nb-accent);
}
</style>
