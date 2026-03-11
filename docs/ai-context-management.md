# AI Context Management for Collaborative Teams
*A practical guide for the screamingface monorepo — informed by real-world team research*

---

## The Problem

When multiple developers vibe-code with AI assistants on the same project, each person's AI session starts cold. Without a shared context strategy, every developer either:
- Re-explains the project from scratch each session
- Gets subtly inconsistent AI behavior (different naming conventions, different assumptions about the stack)
- Accumulates personal AI configs that never benefit the team

This is now a well-documented problem. The major AI coding tools have started codifying solutions, researchers have studied what works, and real teams are publishing what they've learned.

---

## What's Been Standardized (as of early 2026)

### The file format landscape is fragmented, but converging

Every major tool has its own convention:

| Tool | File(s) |
|---|---|
| Claude Code | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/commands/` |
| Cursor | `.cursorrules` (deprecated), `.cursor/rules/*.mdc` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| OpenAI Codex | `AGENTS.md` |
| Aider | `conventions.md` (user-configured) |
| JetBrains Junie | `.junie/guidelines.md` |
| Gemini CLI | `GEMINI.md` |

**AGENTS.md is emerging as a cross-tool open standard** — it appears in over 60,000 GitHub repositories as of early 2026, and OpenAI adopted it for Codex. Worth structuring your context toward even if you're primarily on Claude Code today, since team members may use different tools.

### Claude Code's native hierarchy

Claude reads all applicable `CLAUDE.md` files and merges them, innermost taking precedence:

| File | Scope | Committed? |
|---|---|---|
| `~/.claude/CLAUDE.md` | Global — one dev's preferences, all projects | No (personal) |
| `/CLAUDE.md` (repo root) | Project-wide — all devs, all packages | Yes |
| `/web/CLAUDE.md` | Package-level — web/ only | Yes |
| `CLAUDE.local.md` (anywhere) | Personal overrides at any level — gitignored | No (personal) |

The `CLAUDE.local.md` pattern is the official mechanism for personal context that lives alongside shared context without polluting the repo. Add `CLAUDE.local.md` to your root `.gitignore`.

---

## What Real Teams Are Doing

The following is informed by forum posts, engineering blogs, and academic research.

### 1. Commit shared context to git — near-universal consensus

Across Cursor forums, GitHub discussions, and engineering blogs, the answer to "should this go in version control?" is yes, for the project-level file. Teams describe committed context files as "onboarding docs that work for both humans and AI" — they compound in value over time.

From Atlan's engineering blog on Cursor rules: their team created an org-level `cursor-rules` repo linked to a custom VS Code extension, so all developers stay synced and can submit PRs to propose rule changes.

### 2. The over-specification trap — backed by research

This is the most important and counterintuitive finding: **detailed context files may actively hurt AI performance.**

Two recent papers studied AGENTS.md files across thousands of repositories:
- arxiv 2601.20404 (University of Canterbury/Adelaide): AGENTS.md is associated with *lower* median runtime (−28.64%) and *reduced* output token consumption (−16.58%), while maintaining comparable task completion. A generally positive/neutral result.
- arxiv 2602.11988 (ETH Zurich — Gloaguen, Mündler, Müller, Raychev, Vechev): context files *reduce* task success rates vs. providing no repository context, while increasing inference cost by 20%+. The mechanism: agents follow instructions (run more tests, read more files) but this extra behavior is often unnecessary for the specific task. Within this paper: LLM-generated files degrade performance by ~3% vs. no file; human-written files offer a marginal 4% improvement — but both increase steps and inference costs.

HN discussion: "A 4% improvement from developer-written files is meaningful — LLM-generated context files are the real problem."

**The practical recommendation:** Only include things the AI cannot infer from the codebase itself. If the AI already does it correctly without the instruction, cut it. Write context files yourself — don't generate them with an LLM.

Augment Code's engineering blog describes the anti-pattern: "Your agent's context is a junk drawer — everything thrown in, most of it useless noise at query time."

### 3. Monorepo layering works — keep files close to the code

Datadog's engineering blog documents this pattern for large monorepos: each subpackage ships its own context file, with the closest file in the directory tree taking precedence. Claude Code also supports `claudeMdExcludes` — a glob config to skip CLAUDE.md files from other teams' modules that aren't relevant to your current work.

### 4. Cross-repo sync tooling exists for multi-repo orgs

Two open-source tools address "we have 30 repos and want consistent AI rules":
- **knowhub** — reads a `.knowhubrc`, pulls AI rule files from a central source (private GitHub repo, S3) and distributes them via overwrite or symlink. CI-integrable.
- **ai-rules-sync** — similar, targeting Cursor, Claude Code, Copilot, Codex, Gemini CLI, and Warp simultaneously.

---

## What Belongs in a Context File

Based on the GitHub blog's analysis of 2,500+ repositories and the ETH Zurich research:

### Include
- Custom build/test commands the agent can't infer
- Non-obvious architectural decisions and their rationale
- Naming conventions that deviate from language/framework defaults
- Module ownership — who owns what, where to make changes
- Known gotchas, footguns, and legacy patterns to avoid
- Branch naming and PR/review process

### Exclude
- Generic instructions ("write clean code," "add comments")
- Things the AI already does correctly by default
- API keys, credentials, or internal vulnerability details
- Content that already exists in README or package.json — use `@import` instead
- Anything LLM-generated (adds noise, hurts performance)

---

## Recommended Architecture for This Project

```
screamingface/
├── CLAUDE.md                    # Project-wide: stack, concepts, team, monorepo structure
├── CLAUDE.local.md              # (gitignored) personal overrides — each dev has their own
├── AGENTS.md                    # Mirror of CLAUDE.md for cross-tool compatibility
├── .gitignore                   # includes CLAUDE.local.md
├── .github/
│   └── copilot-instructions.md  # Mirror for any Copilot users on the team
├── docs/
│   └── context/
│       ├── personas.md          # User personas (referenced via @import when relevant)
│       ├── design-system.md     # Bennett's design language, tokens, component patterns
│       ├── url4-protocol.md     # Kevin's protocol spec
│       └── eval-benchmarks.md  # Benchmark definitions, HLE, SOTA targets
├── web/
│   └── CLAUDE.md               # web/-specific: Next.js, charting approach, conventions
├── app/
│   └── CLAUDE.md               # app/-specific: Electron, microservices, Sergey's patterns
└── cloud/
    └── CLAUDE.md               # cloud/-specific: Gates UI, leaderboard data shape
```

Package-level `CLAUDE.md` files use `@import` to pull in relevant `docs/context/` files rather than duplicating content.

---

## Team Split: Shared vs. Personal

| What | Where | Committed? |
|---|---|---|
| Project description, goals, glossary | Root `CLAUDE.md` | Yes |
| Package conventions, patterns, gotchas | Package `CLAUDE.md` | Yes |
| Long-form reference (personas, specs) | `docs/context/*.md` | Yes |
| Personal preferences, experience level | `~/.claude/CLAUDE.md` | No |
| Local path overrides, personal tooling | `CLAUDE.local.md` | No |

---

## Rules for Keeping Context Files Healthy

1. **Treat CLAUDE.md like a contributing guide** — update it when you establish a new pattern. PRs that make architectural decisions should update the relevant CLAUDE.md.

2. **Keep files short** — Claude Code docs warn explicitly: if your file is too long, important rules get lost in the noise. Aim for under 80 lines per file; use `@imports` for long-form reference.

3. **Write instructions, not descriptions** — directive language outperforms descriptive language:
   - Good: "Always use Tailwind for styling. Never use inline styles."
   - Bad: "We generally prefer Tailwind in most cases."

4. **Only write what the AI can't infer** — if it's obvious from the codebase or standard for the framework, skip it.

5. **One source of truth for shared concepts** — root `CLAUDE.md` owns the glossary. Package files use the terms; they don't redefine them.

6. **Personal context never gets committed** — experience level, preferred explanation depth, and workflow preferences live in `~/.claude/CLAUDE.md` or `CLAUDE.local.md`.

---

## For This Team Specifically

| Developer | Primary package | Context notes |
|---|---|---|
| Kyle | `web/` | Personal: React learner — explain component structure and state when relevant |
| Sergey | `app/` | Owns Electron packaging patterns — `app/CLAUDE.md` should reflect his conventions |
| Kevin | `app/` + `cloud/` | url4 protocol owner — keep `docs/context/url4-protocol.md` current |
| Bennett | Design review | May not use Claude Code — `docs/context/design-system.md` serves as shared reference |
| Trask | Product oversight | Personas and goals live in `docs/context/personas.md` |

---

## Immediate Action Items

1. Add `CLAUDE.local.md` to `.gitignore` (each dev will create their own locally)
2. Create `app/CLAUDE.md` — no AI context there yet
3. Create `cloud/CLAUDE.md` — same
4. Create `docs/context/` folder with: `personas.md`, `design-system.md`, `url4-protocol.md`
5. Add `@import` references in package CLAUDE.md files for relevant context docs
6. Each dev sets up `~/.claude/CLAUDE.md` with personal preferences
7. Create `AGENTS.md` at root (mirror of `CLAUDE.md`) for cross-tool compatibility
8. Add `.github/copilot-instructions.md` if any team members use Copilot

---

## Key Sources

- [Claude Code: How Claude Remembers Your Project](https://code.claude.com/docs/en/memory)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)
- [Impact of AGENTS.md Files on AI Coding Agent Efficiency (Univ. Canterbury/Adelaide)](https://arxiv.org/abs/2601.20404)
- [ETH Zurich: Evaluating AGENTS.md — Are Repository-Level Context Files Helpful?](https://arxiv.org/abs/2602.11988)
- [GitHub Blog: How to Write a Great AGENTS.md](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)
- [Datadog: Steering AI Agents in Monorepos with AGENTS.md](https://dev.to/datadog-frontend-dev/steering-ai-agents-in-monorepos-with-agentsmd-13g0)
- [Atlan Engineering: Cursor Rules in Practice](https://blog.atlan.com/engineering/cursor-rules/)
- [Augment Code: Your Agent's Context Is a Junk Drawer](https://www.augmentcode.com/blog/your-agents-context-is-a-junk-drawer)
- [AllStacks: AGENTS.md Files — The Research Says You're Doing Them Wrong](https://www.allstacks.com/blog/agents.md-files-the-research-says-youre-probably-doing-them-wrong)
- [knowhub — cross-repo AI rules sync](https://github.com/yujiosaka/knowhub)
- [CallSphere: Setting Up Claude Code for a Team](https://callsphere.tech/blog/claude-code-team-setup-best-practices)
