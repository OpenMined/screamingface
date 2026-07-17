<script setup lang="ts">
import DocLayout from '@/components/layout/DocLayout.vue'
import NotebookViewer from '@/components/ui/NotebookViewer.vue'
import { sfClientNavigation as navigation } from '@/navigation/sf-client'
import { parseNotebook } from '@/lib/notebook'
import raw from '@/assets/notebooks/00_overview.ipynb?raw'

const notebook = parseNotebook(raw)
</script>

<template>
  <DocLayout :navigation="navigation">
    <NotebookViewer :notebook="notebook" />
  </DocLayout>
</template>
