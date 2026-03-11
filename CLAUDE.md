# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Monorepo Structure
- `apps/web/` — Static marketing website (Next.js, leaderboard chart, install flow)
- `apps/server/` — Python server with plugin-based architecture (FastAPI, uv)
- `packages/` — Shared packages (empty for now)

## The Four App Screens
- **Settings** — configure which AI models are in the ensemble
- **Spend** — view/manage token usage and cost across all models
- **Eval Studio** — run benchmark evals against available models, view results
- **Cache/Log** — browse, search, filter cached AI queries; delete entries; view stats

## Team
- **Bennett** — design lead
- **Sergey** — Server architecture, plugin system (`apps/server/`)
- **Kevin** — app backend, url4 protocol
- **Kyle** — frontend development
- **Trask** — product owner

## Tech Stack
- React + Vite, Tailwind CSS, shadcn/ui — frontend
- Recharts / Chart.js / D3 — data visualization
- TypeScript — frontend language
- Next.js — cloud webapp and marketing site
- FastAPI (Python) + uv — plugin-based server (`apps/server/`)

## Key Concepts
- **url4** — custom protocol; encodes AI task chains as human-readable URLs (DAG-based)
- **Enclave** — secure cloud server running model runners and cache
- **Ensemble** — combining multiple AI models for better results than any single model
- **SOTA** — State of the Art benchmark accuracy scores we're trying to beat
- **Gates** — cloud UI for token sharing between users
