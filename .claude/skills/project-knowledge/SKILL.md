# ScreamingFace — Project Knowledge

## Product

ScreamingFace is an AI ensemble system that routes coding CLI prompts through the best available models (Claude Code, Gemini CLI, Codex, Ollama) to beat SOTA benchmarks. Users install it locally and can share AI credits with friends. Built by OpenMined.

## Team

- **Bennett** — Design lead (branding, visual design for website and app)
- **Sergey** — Electron packaging, local microservices (FastAPI backends), devops
- **Kevin** — App backend, url4 protocol specification/parser/editor
- **Kyle** — Frontend development (static website + local app UI)
- **Trask** — Product owner, daily use/testing/requirements

## Key Concepts

- **url4** — DAG-based protocol encoding AI task chains as human-readable URLs
- **Enclaves** — Secure cloud servers running model runners and cache (CPU-based, auditable)
- **Ensemble** — Combining multiple AI models to achieve better accuracy than any single model
- **SOTA** — State of the Art benchmark accuracy scores the system aims to beat
- **Gates** — Cloud UI for token sharing; users create "models" and share access with rate limits

## Tech Stack

- React + Vite, Tailwind CSS, shadcn/ui — frontend
- Recharts / Chart.js / D3 — data visualization
- TypeScript — frontend language
- Next.js — cloud webapp and marketing site
- Electron — desktop taskbar app (Python-based)
- FastAPI (Python) + uv — microservices
- url4 parser available in Python and JS

## App Screens

- **Settings** — Configure which AI models are in the ensemble
- **Spend** — View/manage token usage and cost across all models
- **Eval Studio** — Run benchmark evals, duplicate SOTA results with available models
- **Cache/Log** — Browse/search/filter cached AI queries, delete entries, view stats

## Deployments

- **web** (`apps/web/`) — Static marketing website (leaderboard chart + install flow)
- **desktop** (`apps/desktop/`) — Electron taskbar app for OSX and Linux
- **cloud** (`apps/cloud/`) — Cloud webapp (Gates token sharing UI, leaderboards)

## Monorepo Structure

```
apps/           — User-facing applications (JS/TS, Electron)
packages/       — Shared libraries (url4, shared types/utils)
services/       — Python FastAPI microservices (uv managed)
```

## Services (Sergey's scope)

- **cache** — Localhost microservice caching LLM queries to disk
- **url4-claude** — Makes Claude Code CLI available via url4
- **url4-gemini** — Makes Gemini CLI available via url4
- **url4-codex** — Makes Codex CLI available via url4
- **url4-ollama** — Makes Ollama CLI available via url4
- **claude2url4** — Enables Claude Code to use any url4 endpoint as its AI endpoint
- **openai2url4** — Enables any OpenAI API client to use any url4 endpoint
- **enclave** — (Week 2+) Cloud enclave runners + cache

## Roadmap

- **Week 1** — "Accessible SOTA": Static website, 8 local microservices, 3-view taskbar app, private beta
- **Week 2** — "Value-for-SOTA": Cloud enclave services, token sharing between users
- **Week 3** — "HN-ready Scale": Load testing, multiple benchmarks, scale testing
- **Week 4** — "HN-ready Security": Security audit, polish, public launch
- **Week 5** — Post-launch debugging
- **Week 6** — Payment layer (Coinbase integration)
- **Weeks 7-22** — Data proxies, browser plugins, user benchmarks, subscriptions, on-prem deployment

## Sergey's Responsibilities by Week

1. 8 local microservices + Electron packaging
2. Enclave model runners + cloud cache
3. Load balancing + scale testing
4. Security audit (white hat)
6. Payment layer integration across microservices
