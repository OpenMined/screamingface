# Screamingface docs — common tasks.
# Run `make` or `make help` to list targets.

.DEFAULT_GOAL := help
.PHONY: help install dev build preview type-check test test-unit test-e2e lint format clean distclean

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies (clean, reproducible)
	npm ci

dev: ## Start the Vite dev server
	npm run dev

build: ## Type-check and build for production
	npm run build

preview: ## Preview the production build locally
	npm run preview

type-check: ## Run vue-tsc type checking
	npm run type-check

test: test-unit ## Run unit tests (alias for test-unit)

test-unit: ## Run unit tests with Vitest
	npm run test:unit

test-e2e: ## Run end-to-end tests with Playwright
	npm run test:e2e

lint: ## Lint and auto-fix (oxlint + eslint)
	npm run lint

format: ## Format source with Prettier
	npm run format

clean: ## Remove build output
	rm -rf dist

distclean: clean ## Remove build output and installed dependencies
	rm -rf node_modules
