import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginOxlint from 'eslint-plugin-oxlint'
import skipFormatting from 'eslint-config-prettier/flat'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,ts,mts,tsx}'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**']),

  ...pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  ...pluginOxlint.buildFromOxlintConfigFile('.oxlintrc.json'),

  // WHY: `vue/multi-word-component-names` exists to stop a user component shadowing a real HTML
  // element (`<Card>`, `<Button>`, `<Header>`). Neither directory below can do that, so the rule
  // is mis-scoped here rather than being relaxed — it still applies everywhere a component could
  // genuinely collide.
  //   - `src/components/ui/` holds shadcn-style primitives (`Collapsible`, `CodeBlock`,
  //     `ApiBlock`, `ImageCarousel`); single-word names are the convention of that library, not
  //     an oversight.
  //   - `src/pages/**/Index.vue` is a section-root ROUTE component (`/sdk`, `/sf-client`). It is
  //     named for its route and never written as a tag, so it has no template identity to clash.
  // Uncovered by CI until OME-738 added a lane, which is why three violations had accumulated:
  // `npm run lint` carries `--fix` and these are not auto-fixable, so it exited 1 unnoticed.
  {
    name: 'app/route-and-primitive-component-names',
    files: ['src/components/ui/**/*.vue', 'src/pages/**/*.vue'],
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },

  skipFormatting,
)
