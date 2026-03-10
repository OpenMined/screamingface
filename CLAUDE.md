# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Monorepo Structure
- `web/` — static marketing website (leaderboard chart, install flow)
- `app/` — local Electron desktop app
- `cloud/` — cloud webapp (Gates/token sharing UI, leaderboards)

## The Four App Screens
- **Settings** — configure which AI models are in the ensemble
- **Spend** — view/manage token usage and cost across all models
- **Eval Studio** — run benchmark evals against available models, view results
- **Cache/Log** — browse, search, filter cached AI queries; delete entries; view stats

## Team
- **Bennett** — design lead
- **Sergey** — Electron packaging, local microservices (localhost backends)
- **Kevin** — app backend, url4 protocol
- **Trask** — product owner

## Tech Stack
- React + Vite
- Tailwind CSS
- Electron (desktop app)
- shadcn/ui (component library)
- Recharts / Chart.js / D3 (data visualization)
- TypeScript (possibly)
- Next.js (possibly, for cloud webapp)

## Key Concepts
- **url4** — custom protocol; encodes AI task chains as human-readable URLs (DAG-based)
- **Enclave** — secure cloud server running model runners and cache
- **Ensemble** — combining multiple AI models for better results than any single model
- **SOTA** — State of the Art benchmark accuracy scores we're trying to beat
- **Localhost microservices** — small FastAPI backends running on the user's machine
