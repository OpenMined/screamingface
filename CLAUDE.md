# Project Context

## The Project
An AI ensemble system combining Claude Code, Gemini CLI, Codex, and Ollama to beat SOTA benchmarks. Users install it locally, it routes coding CLI prompts through the best available models, and they can share AI credits with friends. Built by OpenMined.

## Monorepo Structure (Turborepo-style)
- `apps/web/` — Static marketing website (Next.js, leaderboard chart, install flow)
- `apps/desktop/` — Local Electron desktop taskbar app (Python-based)
- `apps/cloud/` — Cloud webapp (Gates/token sharing UI, leaderboards)
- `packages/url4/` — url4 protocol parser (Python + JS)
- `packages/shared/` — Shared types and utilities
- `services/` — Python FastAPI microservices (uv managed)
  - `cache/` — LLM query cache to disk
  - `url4-claude/` — Claude Code CLI via url4
  - `url4-gemini/` — Gemini CLI via url4
  - `url4-codex/` — Codex CLI via url4
  - `url4-ollama/` — Ollama CLI via url4
  - `claude2url4/` — Claude Code to any url4 endpoint
  - `openai2url4/` — OpenAI API client to any url4 endpoint
  - `enclave/` — (Week 2+) Cloud enclave runners + cache

## The Four App Screens
- **Settings** — configure which AI models are in the ensemble
- **Spend** — view/manage token usage and cost across all models
- **Eval Studio** — run benchmark evals against available models, view results
- **Cache/Log** — browse, search, filter cached AI queries; delete entries; view stats

## Team
- **Bennett** — design lead
- **Sergey** — Electron packaging, local microservices (localhost backends)
- **Kevin** — app backend, url4 protocol
- **Kyle** — frontend development
- **Trask** — product owner

## Tech Stack
- React + Vite, Tailwind CSS, shadcn/ui — frontend
- Recharts / Chart.js / D3 — data visualization
- TypeScript — frontend language
- Next.js — cloud webapp and marketing site
- Electron — desktop taskbar app (Python-based)
- FastAPI (Python) + uv — microservices

## Key Concepts
- **url4** — custom protocol; encodes AI task chains as human-readable URLs (DAG-based)
- **Enclave** — secure cloud server running model runners and cache
- **Ensemble** — combining multiple AI models for better results than any single model
- **SOTA** — State of the Art benchmark accuracy scores we're trying to beat
- **Gates** — cloud UI for token sharing between users
