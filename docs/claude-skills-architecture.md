# Claude Skills Architecture — OpenMined Org-Wide System
**Date:** March 2026
**Status:** Proposal (v2)
**Repo:** https://github.com/OpenMined/skills

---

## Purpose

This document proposes an architecture for OpenMined's shared Claude Code skills system. The goal: any team member, on any OpenMined project, gets consistent brand voice, audience targeting, and task playbooks — with the ability to override anything at the project level.

The system should be:
- **Scalable** — works for 2 projects or 20
- **Flexible** — projects can override org defaults without forking
- **Self-enforcing** — no secret knowledge required to use it correctly
- **Self-documenting** — the system teaches itself through descriptions and structure

---

## Core Concept: Three Layers

```
┌─────────────────────────────────────────────┐
│  Layer 1: Org Knowledge    (shared context)  │  ← Who we are, who we talk to, how we sound
├─────────────────────────────────────────────┤
│  Layer 2: Skills           (task playbooks)  │  ← What we do: /copy, /webpage, /proposal...
├─────────────────────────────────────────────┤
│  Layer 3: Project Overrides (local rules)    │  ← What's different here
└─────────────────────────────────────────────┘
```

**Layer 1** is always available. **Layer 2** loads when you invoke a skill. **Layer 3** is detected automatically per-project. No layer needs to know about the others' internals — they compose through Claude Code's existing precedence system.

---

## Layer 1: Org Knowledge (the skills repo)

### Repo Structure

```
OpenMined/skills/
├── CLAUDE.md                              # Repo-level instructions for contributors
│
├── context/                               # ── Shared knowledge ──
│   ├── voice.md                           # How we sound (tone, register, do/don't)
│   ├── terminology.md                     # Canonical terms across all products
│   ├── values.md                          # Messaging principles (mediator framing, etc.)
│   ├── openmined.md                       # Who we are, history, mission, PySyft
│   ├── tech-glossary.md                   # url4, enclave, ensemble, SOTA, federated learning
│   │
│   ├── audiences/                         # Org-level audience archetypes
│   │   ├── technical-developer.md         # The builder (base archetype)
│   │   ├── policy-leader.md              # The amplifier (base archetype)
│   │   └── general-public.md             # The curious outsider (base archetype)
│   │
│   └── references/                        # Pointers to deeper material
│       ├── abc-thesis-summary.md          # Key claims from attribution-based-control.ai
│       └── policy-landscape.md            # EU AI Act, GDPR, exec orders — shared framing
│
├── skills/                                # ── Task playbooks ──
│   ├── copy/
│   │   └── SKILL.md                       # /copy — rewrite or generate marketing copy
│   ├── webpage/
│   │   └── SKILL.md                       # /webpage — create a new page
│   ├── starter-app/
│   │   └── SKILL.md                       # /starter-app — scaffold a new project
│   ├── proposal/
│   │   └── SKILL.md                       # /proposal — generate a client proposal
│   ├── media/
│   │   └── SKILL.md                       # /media — press releases, social, comms
│   └── review/
│       └── SKILL.md                       # /review — check any content against org rules
│
└── onboarding.md                          # How to set up, what's here, how it works
```

### Why context/ is top-level

Every skill needs to know the voice. Every skill might need an audience persona. Every skill might reference the tech glossary. Context is shared infrastructure, not owned by any single task. Putting audiences or references inside a `/copy` folder would mean other skills either duplicate them or reach into a sibling skill's directory — both are wrong.

---

## Layer 2: Skills (task playbooks)

Each skill is a directory with a `SKILL.md` file that defines the slash command, its description, and its instructions. Skills pull in shared context from `context/` using dynamic injection (`!`command`` syntax).

### How skills reference shared context

```yaml
# skills/copy/SKILL.md
---
name: copy
description: "Generate or rewrite copy following OpenMined's voice and audience targeting"
argument-hint: "[what to write] [audience if known]"
---

## Voice
!`cat context/voice.md`

## Terminology
!`cat context/terminology.md`

## Audience Weighting
If a persona weighting guide exists in this project (`personas/weighting-guide.md`),
read it to determine which audience to target. If not, ask which audience before writing.

## Org Audiences
!`cat context/audiences/technical-developer.md`
!`cat context/audiences/policy-leader.md`

## Task
$ARGUMENTS
```

### Which skills load which context

| Skill | Loads from context/ |
|-------|-------------------|
| `/copy` | voice, terminology, audiences, values |
| `/webpage` | voice, terminology, tech-glossary, audiences |
| `/starter-app` | tech-glossary, terminology |
| `/proposal` | voice, values, openmined, audiences |
| `/media` | voice, terminology, values, policy-landscape |
| `/review` | voice, terminology, values (checks against all three) |

Each skill loads only what it needs. A `/starter-app` invocation doesn't need to load audience personas. A `/media` invocation doesn't need the tech glossary. This keeps token usage reasonable.

### Planned skills

| Skill | Purpose | Primary users |
|-------|---------|--------------|
| `/copy` | Generate or rewrite marketing copy | Kyle, content contributors |
| `/webpage` | Create a new page following brand + tech standards | Kyle, frontend devs |
| `/starter-app` | Scaffold a new project with OpenMined's stack | Sergey, Kevin, new devs |
| `/proposal` | Generate a client or grant proposal | Trask, business team |
| `/media` | Press releases, social posts, comms | Lacey, comms team |
| `/review` | Check any content against org voice + terminology | Everyone |

---

## Layer 3: Project Overrides

Each project repo handles overrides through its own `.claude/` directory. No special file format — just standard CLAUDE.md and rules files that Claude already knows how to load.

### Example: screamingface project overrides

```
screamingface/
├── CLAUDE.md                              # Project context + pointer to overrides
├── .claude/
│   └── rules/
│       ├── voice-override.md             # More technical than org default
│       ├── terminology-override.md       # "credit sharing" not "token sharing"
│       └── messaging.md                  # Mediator framing, no timeframe specifics
├── personas/
│   ├── persona-audience-1.md             # Project-specific refinement of org archetype
│   ├── persona-audience-2.md
│   └── weighting-guide.md               # Which personas apply where in THIS project
└── ...
```

### How overrides work

Claude loads the project's CLAUDE.md and rules at session start. When a skill fires, it loads org context from the skills repo. The project rules take precedence because they're in the project scope (higher priority than plugin-level content). No special override syntax needed — Claude's existing precedence handles it:

```
Project CLAUDE.md + .claude/rules/    ← wins on conflict
         ↓
Skill content (from plugin)           ← org defaults
         ↓
Org context/ files (loaded by skill)  ← base knowledge
```

### Example override file

```markdown
# Voice Override: screamingface
# .claude/rules/voice-override.md

These rules extend the org voice guide for this project.

## More technical than org default
- Audience 1 is developers who run benchmarks and read arxiv
- Code examples, CLI commands, and benchmark numbers are appropriate
- Don't soften technical language for accessibility — this audience wants precision

## Banned words (in addition to org list)
- "cutting edge", "powerful", "seamless", "revolutionary"
- Any specific timeframe for the window (no "two years", "18 months", etc.)
- "free market" in any societal framing

## Required framing
- OpenMined as mediator, never as combatant
- Acknowledge both open-source and closed-model arguments as legitimate
- The ensemble resolves the tradeoff — nobody has to lose
```

A project can override voice, terminology, or any other org default just by adding a rules file. No special "override format" to learn. It's CLAUDE.md files all the way down.

---

## Distribution & Installation

### How the team gets the skills

The skills repo is distributed as a Claude Code plugin. Two installation paths:

**Manual (one-time):**
```bash
/plugin install openmined-skills
```

**Automatic (via project settings):**

Each project repo commits a `.claude/settings.json` that auto-installs the plugin:

```json
{
  "enabledPlugins": {
    "openmined-skills@openmined-marketplace": true
  }
}
```

New team member clones a project repo, opens Claude Code, and the skills are available. They type `/` and see the full list with descriptions.

### Updates

When the skills repo is updated (new context, revised voice guide, new skill), every project gets the update on next Claude Code session. No manual sync. No version pinning unless explicitly needed.

---

## Onboarding

### For a new team member

1. Clone any OpenMined project repo
2. Open Claude Code
3. Skills auto-install via project settings
4. Type `/` to see available skills
5. Type `/copy help` or `/review help` to see what each skill does
6. Start working — org voice, terminology, and audiences are loaded automatically

No setup guide to follow. No config files to copy. No Slack thread to find. The system bootstraps itself from the project's committed settings.

### For a new project

1. Create the repo
2. Add `.claude/settings.json` with the plugin reference
3. Add a `CLAUDE.md` with project context
4. Optionally add `.claude/rules/` files for any overrides
5. Optionally add `personas/` for project-specific audience refinements

The project immediately inherits all org-wide skills and context. Overrides are opt-in — if you don't add any, you get the org defaults.

---

## Self-Enforcement

The system requires no secret knowledge for three reasons:

### 1. Skills are self-documenting

Each SKILL.md has a `description` field that shows up in `/` autocomplete. The skill itself loads the context it needs — the user doesn't have to know which files to read or which guidelines apply.

### 2. The override system is just CLAUDE.md

No new concepts to learn. If you know how CLAUDE.md works (and every Claude Code user does), you know how overrides work. Put a file in `.claude/rules/`, it loads automatically.

### 3. The `/review` skill enforces consistency

Any team member can run `/review` on any content and it checks against org voice, terminology, and values — plus any project overrides. This is the guard rail that catches drift without requiring anyone to memorize the rules.

The only thing a team member needs to know is that the skills exist — and that's solved by auto-installation. After that, the system teaches itself.

---

## Decision Guide: What Goes Where

| Question | Answer |
|----------|--------|
| Is it true for ALL OpenMined projects? | `context/` in the skills repo |
| Is it a task someone invokes? | `skills/` in the skills repo |
| Is it specific to one product? | `.claude/rules/` in the project repo |
| Is it a refined version of an org archetype? | `personas/` in the project repo |
| Is it deep reference material (full thesis, research cohorts)? | Project repo `docs/` or `personas/` |
| Is it a summary that multiple skills might need? | `context/references/` in the skills repo |

---

## Relationship to Existing screamingface Assets

screamingface already has most of Layer 3 built:

| Asset | Current location | Role in this system |
|-------|-----------------|-------------------|
| `personas/weighting-guide.md` | Project repo | Project-level audience routing (Layer 3) |
| `personas/persona-audience-1.md` | Project repo | Project refinement of org "technical-developer" archetype |
| `personas/persona-audience-2.md` | Project repo | Project refinement of org "policy-leader" archetype |
| `personas/abc-citations/` | Project repo | Deep reference material (not in skills repo) |
| `personas/time100-ai/` | Project repo | Deep reference material (not in skills repo) |
| `CLAUDE.md` | Project repo | Project context + override pointers (Layer 3) |
| `web/CLAUDE.md` | Project repo | Package-specific rules (Layer 3) |

What would move to the skills repo (as org-level context):
- A `voice.md` distilled from the patterns in screamingface's copy work
- A `terminology.md` of canonical OpenMined terms
- A `values.md` capturing the mediator framing and other messaging principles
- Base audience archetypes that screamingface's personas refine
- An `openmined.md` with the org description (currently scattered across CLAUDE.md files)

---

## Next Steps

1. **Draft the core context files** — `voice.md`, `terminology.md`, `values.md` based on screamingface's existing copy and persona work
2. **Write the first SKILL.md files** — `/copy` and `/review` as the initial skills
3. **Test the override system** — set up screamingface as the first project with Layer 3 overrides
4. **Share with team** — get feedback from Trask, Bennett, and the broader OpenMined team on the architecture
5. **Build out remaining skills** — `/webpage`, `/starter-app`, `/proposal`, `/media` based on team needs

---

*Architecture proposal by Kyle Numann, March 2026. Developed in collaboration with Claude Code for the OpenMined skills system at github.com/OpenMined/skills.*
