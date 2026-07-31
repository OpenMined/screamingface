# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Screamingface documentation site — a Vue 3 + TypeScript + Vite application. The
baseline chrome (navbar, themeable sidebar/doc layout, and a data-driven
navigation system) was ported from `syft-space-hub-docs`; the page content is
being built out per section.

## Development Commands

- **Dev server**: `npm run dev`
- **Build**: `npm run build` (type-check + Vite build)
- **Preview**: `npm run preview`
- **Type-check**: `npm run type-check` (`vue-tsc --noEmit`)
- **Lint**: `npm run lint` (oxlint + eslint, auto-fix)
- **Format**: `npm run format` (Prettier, `src/`)

There is no automated test setup in this project.

## Stack

- Vue 3 + Vue Router + Pinia
- Tailwind CSS v4 (via `@tailwindcss/vite`) with the theme tokens in `src/style.css`
- `lucide-vue-next` for icons, `prismjs` for code highlighting, `markdown-it` for
  notebook markdown
- Path alias `@/` → `src/`
- Type-checking uses a single `tsconfig.json` (extends `@vue/tsconfig`) covering
  `src/**` plus the config files (`vite.config.ts`, `eslint.config.ts`)

## Architecture

- `src/App.vue` — shell: `<TheNavbar />` + `<RouterView />`
- `src/components/layout/TheNavbar.vue` — sticky top nav (brand, product links [Home / SF Client / SDK], theme toggle, GitHub)
- `src/components/layout/DocLayout.vue` — sidebar + optional page header + content slot + prev/next buttons (`title` is optional; the header is skipped when omitted). A navigation section whose `title` is an empty string renders no group heading, so an item can sit ungrouped above the labelled sections.
- `src/components/ui/` — reusable content components: `CodeBlock`, `TabbedCodeBlock`, `ApiBlock`, `Collapsible`, `ImageCarousel`, `NotebookViewer`
- `src/composables/` — reusable logic: `useCopy` (clipboard + "Copied!" feedback), `useHighlight` (central Prism setup + `highlight()`), `useDocNavigation` (sidebar active-state + prev/next from a nav tree), `useCarousel` (index + auto-advance)
- `src/stores/` — Pinia stores for shared reactive state: `theme` (`isDark` state, `theme` getter, dark/light + localStorage persistence) and `codeLang` (shared code-tab language across `TabbedCodeBlock`s)
- `src/lib/` — framework-agnostic helpers: `utils.ts` (`cn` class merge) and `notebook.ts` (nbformat types + pure helpers for `NotebookViewer`)
- `src/pages/` — route components; `src/router/index.ts` — routes
- `src/navigation/` — one data file per documentation section (drives the sidebar + prev/next)
- `src/style.css` — Tailwind import + light/dark theme tokens + prose styling (includes `@tailwindcss/typography` with prose variables mapped to the theme tokens)

### Pages & routes

| Route | Component |
|---|---|
| `/` | `src/pages/HomePage.vue` |
| `/sf-client` | `src/pages/sf-client/Index.vue` |
| `/sf-client/installation` | `src/pages/sf-client/InstallationPage.vue` |
| `/sf-client/quickstartPage` | `src/pages/sf-client/QuickstartPage.vue` |
| `/sdk` | `src/pages/sdk/Index.vue` |

### NotebookViewer

`src/components/ui/NotebookViewer.vue` renders a Jupyter `.ipynb` (parsed via
`src/lib/notebook.ts`): markdown cells → prose (`markdown-it`), code cells →
`In [n]` + copy + collapse (Prism), outputs handle html/text/image/error/stream.
It supports a `showTitle` toggle and rewrites inter-notebook links via
`NOTEBOOK_ROUTES`. It is kept for reuse but is **not currently wired to a page**.

## Navigation System

The sidebar and prev/next buttons are driven by shared data files in
`src/navigation/`, one file per documentation section.

| File | Export | Used by | Entries |
|---|---|---|---|
| `src/navigation/sf-client.ts` | `sfClientNavigation` | All `/sf-client/*` pages | Overview (ungrouped), then **Get Started**: Quickstart, Installation |
| `src/navigation/sdk.ts` | `sdkNavigation` | All `/sdk/*` pages | Overview |

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
