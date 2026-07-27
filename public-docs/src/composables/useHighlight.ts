import Prism from 'prismjs'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-javascript'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import '@/assets/prism-theme.css'

// Central Prism setup. To support another language, add its
// `prismjs/components/prism-<lang>` import above — every code block picks it up.
function escapeHtml(str: string) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function useHighlight() {
  // Returns HTML safe to render with v-html: Prism-highlighted markup when the
  // language is known, otherwise the escaped source (never raw, unescaped code).
  const highlight = (code: string, language: string): string => {
    const key = language.toLowerCase()
    try {
      const grammar = Prism.languages[key]
      if (grammar) return Prism.highlight(code, grammar, key)
    } catch (error) {
      console.warn('Failed to highlight code:', error)
    }
    return escapeHtml(code)
  }

  return { highlight }
}
