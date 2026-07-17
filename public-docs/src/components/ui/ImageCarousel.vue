<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useCarousel } from '@/composables/useCarousel'

interface MediaItem {
  src: string
  alt: string
  caption?: string
  isVideo?: boolean
}

interface Props {
  images: Array<MediaItem>
}

const props = defineProps<Props>()

const { currentIndex, next, prev, goTo, startAutoAdvance, stopAutoAdvance, handleManualNavigation } =
  useCarousel(() => props.images.length)

const currentMedia = computed(() => props.images[currentIndex.value])
</script>

<template>
  <div 
    v-if="currentMedia" 
    class="relative rounded-xl overflow-hidden border border-border bg-card/50"
    @mouseenter="stopAutoAdvance"
    @mouseleave="startAutoAdvance"
  >
    <!-- Media container -->
    <div class="relative aspect-video">
      <Transition name="fade" mode="out-in">
        <video
          v-if="currentMedia.isVideo"
          :key="'video-' + currentIndex"
          :src="currentMedia.src"
          class="w-full h-full object-cover"
          autoplay
          loop
          muted
          playsinline
        />
        <img
          v-else
          :key="'img-' + currentIndex"
          :src="currentMedia.src"
          :alt="currentMedia.alt"
          class="w-full h-full object-cover"
        />
      </Transition>
      
      <!-- Navigation arrows -->
      <button
        v-if="images.length > 1"
        @click="handleManualNavigation(prev)"
        class="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 hover:bg-black/70 flex items-center justify-center text-white transition-colors"
        aria-label="Previous image"
      >
        <ChevronLeft class="w-5 h-5" />
      </button>
      <button
        v-if="images.length > 1"
        @click="handleManualNavigation(next)"
        class="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 hover:bg-black/70 flex items-center justify-center text-white transition-colors"
        aria-label="Next image"
      >
        <ChevronRight class="w-5 h-5" />
      </button>
    </div>
    
    <!-- Caption and dots -->
    <div class="p-3 flex items-center justify-between gap-4">
      <p v-if="currentMedia.caption" class="text-sm text-muted-foreground">
        {{ currentMedia.caption }}
      </p>
      <div v-else class="flex-1"></div>
      
      <!-- Dot indicators -->
      <div v-if="images.length > 1" class="flex items-center gap-1.5">
        <button
          v-for="(_, index) in images"
          :key="index"
          @click="handleManualNavigation(() => goTo(index))"
          :class="[
            'w-2 h-2 rounded-full transition-colors',
            index === currentIndex ? 'bg-primary' : 'bg-muted-foreground/30 hover:bg-muted-foreground/50'
          ]"
          :aria-label="`Go to image ${index + 1}`"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
