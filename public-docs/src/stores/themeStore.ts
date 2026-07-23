import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'

// Global light/dark theme state. The initial value is read from the class that
// index.html sets before the app mounts (from localStorage), so there is no
// flash of the wrong theme. Changes are persisted back to localStorage.
export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(
    typeof window !== 'undefined'
      ? document.documentElement.classList.contains('dark')
      : true,
  )

  const theme = computed(() => (isDark.value ? 'dark' : 'light'))

  const toggleTheme = () => {
    isDark.value = !isDark.value
  }

  const setTheme = (dark: boolean) => {
    isDark.value = dark
  }

  watch(
    isDark,
    (dark) => {
      if (typeof window === 'undefined') return
      document.documentElement.classList.toggle('dark', dark)
      localStorage.setItem('theme', dark ? 'dark' : 'light')
    },
    { immediate: true },
  )

  return { isDark, theme, toggleTheme, setTheme }
})
