<script setup lang="ts">
import { RouterView } from 'vue-router'
import TheNavbar from '@/components/layout/TheNavbar.vue'
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <TheNavbar />
    <main class="flex-1">
      <RouterView />
    </main>
  </div>
</template>
