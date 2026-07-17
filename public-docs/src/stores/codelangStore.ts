import { ref } from 'vue'
import { defineStore } from 'pinia'

const DEFAULT_LANG = 'python'

// Shared "active language" for multi-language code blocks, so that switching the
// tab in one TabbedCodeBlock switches every block on the page in sync. Reset to
// the default on route changes (see DocLayout).
export const useCodeLangStore = defineStore('codeLang', () => {
  const activeLang = ref(DEFAULT_LANG)

  const setLang = (lang: string) => {
    activeLang.value = lang
  }

  const reset = () => {
    activeLang.value = DEFAULT_LANG
  }

  return { activeLang, setLang, reset }
})
