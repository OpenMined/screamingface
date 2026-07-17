# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Screamingface documentation site — a Vue 3 + TypeScript + Vite application. The
baseline chrome (navbar, themeable sidebar/doc layout, and a data-driven
navigation system) was ported from `syft-space-hub-docs`; only the page content
differs.

## Development Commands

- **Dev server**: `npm run dev`
- **Build**: `npm run build` (type-check + Vite build)
- **Preview**: `npm run preview`
- **Unit tests**: `npm run test:unit` (Vitest — specs in `tests/`)
- **E2E tests**: `npm run test:e2e` (Playwright — specs in `tests/e2e/`)
- **Lint**: `npm run lint`

## Stack

- Vue 3 + Vue Router + Pinia
- Tailwind CSS v4 (via `@tailwindcss/vite`) with the theme tokens in `src/style.css`
- `lucide-vue-next` for icons, `prismjs` for code highlighting
- Path alias `@/` → `src/`

## Architecture

- `src/App.vue` — shell: `<TheNavbar />` + `<RouterView />`
- `src/components/layout/TheNavbar.vue` — sticky top nav (brand, product links, theme toggle, Roadmap/GitHub)
- `src/components/layout/DocLayout.vue` — sidebar + page header + content slot + prev/next buttons
- `src/components/ui/` — reusable content components: `CodeBlock`, `TabbedCodeBlock`, `ApiBlock`, `Collapsible`, `ImageCarousel`
- `src/composables/` — reusable logic: `useCopy` (clipboard + "Copied!" feedback), `useHighlight` (central Prism setup + `highlight()`), `useDocNavigation` (sidebar active-state + prev/next from a nav tree), `useCarousel` (index + auto-advance)
- `src/stores/` — Pinia stores for shared reactive state: `theme` (`isDark` state, `theme` getter, dark/light + localStorage persistence) and `codeLang` (shared code-tab language across `TabbedCodeBlock`s)
- `src/pages/` — route components (stubs, generated from the nav data); `src/router/index.ts` — routes
- `src/navigation/` — one data file per documentation section (drives the sidebar + prev/next)
- `src/style.css` — Tailwind import + light/dark theme tokens + prose styling

## Navigation System

The sidebar and prev/next buttons are driven by shared data files in
`src/navigation/`, one file per documentation section.

| File | Export | Used by |
|---|---|---|
| `src/navigation/sf-client.ts` | `sfClientNavigation` | All `/sf-client/*` pages |
| `src/navigation/sdk.ts` | `sdkNavigation` | All `/sdk/*` pages |

The `/sf-client` and `/sdk` sections were imported from `syft-space-hub-docs` as
**stub pages** — real navigation structure, placeholder content to be filled in.

**How pages consume it:**

```ts
import { sfClientNavigation as navigation } from '@/navigation/sf-client'
```

The `as navigation` alias keeps templates uniform — every page passes
`:navigation="navigation"` to `DocLayout`.

**How prev/next works:** `DocLayout` flattens the navigation tree
(sections → items → children) into a sequential list and computes the previous
and next page from the current route. Adding a page to a nav file automatically
gives it prev/next buttons — no per-page configuration.

**Adding a new page:**

1. Create the Vue page under `src/pages/<section>/`, rendering it inside `DocLayout`.
2. Add a route in `src/router/index.ts`.
3. Add the page entry to the relevant `src/navigation/<section>.ts` file
   (top-level item or child of an existing item).
4. Import the shared navigation in the new page:
   `import { <export> as navigation } from '@/navigation/<section>'`.

**Adding a new section:**

1. Create `src/navigation/<section>.ts` exporting a `<section>Navigation` array.
2. Add the section's routes in `src/router/index.ts`.
3. Add a top-level link to the section in `src/components/layout/TheNavbar.vue`
   (`products` array + `currentProduct` computed).
4. Each page in the new section imports from that navigation file.
