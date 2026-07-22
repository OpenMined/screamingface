# screamingface-docs

Documentation site for ScreamingFace — a Vue 3 + TypeScript + Vite single-page app.

## Stack

- Vue 3 + Vue Router + Pinia
- Vite (dev/build) with `@tailwindcss/vite` (Tailwind CSS v4); theme tokens in `src/style.css`
- `prismjs` for code highlighting, `lucide-vue-next` for icons
- ESLint (with oxlint) + Prettier
- Path alias `@/` → `src/`

## Setup

```sh
npm install
```

## Development

```sh
npm run dev          # start the Vite dev server (hot reload)
```

## Build

```sh
npm run build        # type-check (vue-tsc) + production build
npm run preview      # preview the production build locally
```

## Quality

```sh
npm run type-check   # vue-tsc --noEmit
npm run lint         # oxlint + eslint (auto-fix)
npm run format       # prettier --write src/
```

## Project layout

- `src/App.vue` — shell (`<TheNavbar />` + `<RouterView />`)
- `src/pages/` — route components; `src/router/index.ts` — routes
- `src/components/layout/` — navbar + doc layout; `src/components/ui/` — reusable content components
- `src/composables/` — reusable logic (copy, highlight, doc navigation, carousel)
- `src/stores/` — Pinia stores (theme, code-tab language)
- `src/navigation/` — data files that drive the sidebar + prev/next per section
- `src/lib/` — framework-agnostic helpers
- `src/style.css` — Tailwind import + light/dark theme tokens + prose styling

Type checking uses a single `tsconfig.json` (extends `@vue/tsconfig`), covering `src/**`
and the config files.
