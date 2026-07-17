# screamingface-docs

## Quick start (Makefile)

Common tasks are wrapped in the [Makefile](Makefile). Run `make` (or `make help`)
to list every target.

```sh
make install     # install dependencies (npm ci)
make dev         # start the Vite dev server
make build       # type-check and build for production
make preview     # preview the production build
make type-check  # run vue-tsc type checking
make test        # run unit tests (Vitest)
make test-e2e    # run end-to-end tests (Playwright)
make lint        # lint and auto-fix (oxlint + eslint)
make format      # format with Prettier
make clean       # remove build output (dist)
make distclean   # remove build output and node_modules
```

The underlying npm scripts are documented below.

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

### Run Unit Tests with [Vitest](https://vitest.dev/)

```sh
npm run test:unit
```

### Run End-to-End Tests with [Playwright](https://playwright.dev)

```sh
# Install browsers for the first run
npx playwright install

# When testing on CI, must build the project first
npm run build

# Runs the end-to-end tests
npm run test:e2e
# Runs the tests only on Chromium
npm run test:e2e -- --project=chromium
# Runs the tests of a specific file
npm run test:e2e -- tests/example.spec.ts
# Runs the tests in debug mode
npm run test:e2e -- --debug
```

### Lint with [ESLint](https://eslint.org/)

```sh
npm run lint
```
