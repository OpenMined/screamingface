import { ref, onMounted, onUnmounted, toValue, type MaybeRefOrGetter } from 'vue'

// Index state + auto-advance for a carousel of `count` items. Auto-advance
// pauses on manual navigation and resumes after `resumeDelay`. Timers are
// cleaned up on unmount.
export function useCarousel(
  count: MaybeRefOrGetter<number>,
  options: { interval?: number; resumeDelay?: number } = {},
) {
  const { interval = 3000, resumeDelay = 5000 } = options
  const currentIndex = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  let resumeTimer: ReturnType<typeof setTimeout> | null = null

  const len = () => toValue(count)

  const next = () => {
    const n = len()
    if (n > 0) currentIndex.value = (currentIndex.value + 1) % n
  }

  const prev = () => {
    const n = len()
    if (n > 0) currentIndex.value = (currentIndex.value - 1 + n) % n
  }

  const goTo = (index: number) => {
    currentIndex.value = index
  }

  const stopAutoAdvance = () => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  const startAutoAdvance = () => {
    stopAutoAdvance()
    if (len() > 1) timer = setInterval(next, interval)
  }

  // Run `action`, then resume auto-advance after a pause.
  const handleManualNavigation = (action: () => void) => {
    stopAutoAdvance()
    action()
    if (resumeTimer) clearTimeout(resumeTimer)
    resumeTimer = setTimeout(startAutoAdvance, resumeDelay)
  }

  onMounted(startAutoAdvance)
  onUnmounted(() => {
    stopAutoAdvance()
    if (resumeTimer) clearTimeout(resumeTimer)
  })

  return {
    currentIndex,
    next,
    prev,
    goTo,
    startAutoAdvance,
    stopAutoAdvance,
    handleManualNavigation,
  }
}
