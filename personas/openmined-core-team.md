# OpenMined Core Team
**Type:** Internal
**Priority:** P0 (build for now)

## Identity

The ~32-person OpenMined team spanning engineering, product, policy, partnerships, and operations. They are the first real users of screamingface — the internal beta audience before any public launch. Most are technical or technically fluent. They work across multiple "bets" (product initiatives) including NSAI, Beach, Influencers, Genetics, BioVault, and Federated Learning. They present weekly at "Heartbeat" meetings and collaborate heavily via Slack, Google Docs, Miro, and Asana. Distributed globally (US East/West, Europe, India, Australia).

This is not a homogeneous group — it ranges from the Executive Director building prototypes, to policy leads, to a new Head of Engineering focused on scaling, to product managers running pilot partnerships. What they share: mission alignment (privacy-preserving AI), comfort with early/rough products, and willingness to dogfood.

## Departments and Roles

- **Leadership:** Executive Director, COO, Head of Engineering (recently joined)
- **Engineering (~10):** Building SyftBox, SyftHub, enclaves, protocols. A mix of senior systems engineers, infrastructure leads, and full-stack developers.
- **Product (~3-4):** Pilots/product leads running partner engagements and product bets (NSAI, Influencers, etc.)
- **Design/Marketing (~1-2):** Design lead who also handles inbound lead profiling and marketing ops
- **Policy/Partnerships (~3):** Policy research, fundraising, grant partnerships
- **Operations (~2):** Heartbeat coordination, operations management
- **Research (~3-4):** Cryptography/MPC, ML (ensemble SOTA work), genetics
- **Community (~2):** Federated learning community, developer relations

## Technical Profile

- **Primary languages:** Python, TypeScript/JavaScript
- **Infrastructure:** SyftBox, PySyft, FastAPI, Docker, Electron, enclaves (CPU and GPU)
- **AI tools in active use:** Claude Code, Gemini CLI, Codex — several team members are heavy daily users
- **Collaboration tools:** Slack (heavily), GitHub, Google Docs/Slides, Miro, Asana, Figma, Loom
- **OS:** macOS dominant, Linux for infra/engineering
- **Technical range:** Wide — from "design lead shipping code with Claude Code" to "PhD building encrypted vector databases and MPC protocols"

## Relationship to AI Coding Tools

This team is deeply embedded in AI coding tools. Many use Claude Code, Gemini CLI, or Codex daily for real work. Key dynamics:

- **Engineers** use them for implementation, debugging, code review, and prototyping. One engineer built a CLI tool for Asana entirely with Claude. Others think deeply about agent architectures and model ensembling.
- **Non-engineers** use them as force multipliers. The design lead ships real frontend code via Claude Code despite not having a traditional engineering background. Leadership prototypes rapidly.
- **Everyone** experiences the core pain: credit limits, inconsistent quality across providers, switching costs between tools. These are not theoretical problems — they hit them daily.
- The team is already intellectually bought in on ensembling (internal research has proven ensemble SOTA; the ED has years of research in this area). They don't need convincing that it works — they need to see it work smoothly in their own workflows.

## Pain Points

1. **Credit fragmentation** — Everyone has separate subscriptions across providers. Can't pool or share unused tokens. When one person runs out, they stop working even though a colleague may have dormant credits.
2. **No single best model** — Different tasks favor different models. Currently requires manual switching.
3. **Can't prove quality claims** — Leadership wants reproducible SOTA results for academic and marketing purposes. The team wants verifiable benchmarks, not marketing.
4. **Tool switching friction** — Context-switching between Claude Code, Gemini, and Codex for different strengths.
5. **Scaling research to product** — Internal research proved ensemble SOTA; now they need it in a usable product form.
6. **Onboarding overhead** — New team members need to get up to speed fast. A one-command install matters.

## Value Triggers

- Seeing ensemble beat any single model on a benchmark they care about
- Using their normal coding CLI and getting measurably better results
- Sharing unused Claude/Gemini credits with a teammate who ran out
- One-command install that auto-detects everything on their machine
- Running an eval locally in the Eval Studio and matching published SOTA
- "It just works better without being noticeably slower" (from devplan)

## Messaging That Resonates

- **"SOTA on your laptop"** — direct, provable, exciting
- **"No single company should own the most powerful model"** — mission-aligned with OpenMined's core belief
- **"Models so fast you'll scream"** — fun, irreverent brand energy
- **Concrete proof:** benchmark numbers, reproducible eval results, open source
- **The 1-2-3 install flow** — leadership specifically praised this as great UX
- **"Share credits with friends"** — immediately resonates with anyone who's hit rate limits
- **Internal-first language:** "we all use the tool as our own daily driver. Fix what you don't like." (from devplan)

## Messaging That Falls Flat

- Vague AI hype ("revolutionary", "next-gen", "groundbreaking")
- Enterprise-speak ("solution", "platform", "digital transformation")
- Over-explaining what ensembling is — this team already knows
- Privacy/governance framing *for this product* — they care about it broadly (it's OpenMined's mission), but for screamingface the hook is performance and cost, not privacy
- Anything that feels like marketing to marketers — they want to see it work, not hear about it

## Design Implications

**Website:**
- The SOTA claim must be backed by real, verifiable data — the leaderboard chart is evidence, not decoration
- Install flow should feel effortless — one command, done
- Clean, dark, technical aesthetic. Let the data speak.
- Password gate makes sense for now — team knows they're seeing something pre-launch

**App (Electron):**
- **Eval Studio** is the "prove it" feature — must be prominent. This team will actually run evals.
- **Spend tracking** should show value: "you saved $X by ensembling" or "you used Y% fewer tokens for the same quality"
- **Cache/Log** is a power-user feature this team will use daily — browse, search, filter cached queries
- **Settings** should auto-detect and configure models — manual setup is friction. "All model sources are automatically detected."
- Must work for both heavy CLI users (engineers) and lighter users (product, policy folks who use AI tools occasionally)

**Cloud/Gates:**
- Token sharing UX must be dead simple — "send a link, friend clicks it, done"
- Rate limiting controls matter (time of day, % of budget) — this team thinks about resource allocation
- Leaderboard page showing multiple benchmarks, not just one

## Culture and Communication Style

- **High trust, low ceremony.** PRs get merged fast with informal review. "feel free to merge things... i'm not feeling any territorial vibes"
- **Show > tell.** Weekly heartbeat presentations with concrete demos. They ship and share, not just discuss.
- **Humor and irreverence.** The product is named after a screaming face emoji. Internal passwords are jokes. The vibe is playful and fast.
- **Mission-driven but practical.** Deeply believe in privacy-preserving AI, but right now they need SOTA performance and a smooth install.
- **Everyone builds.** Even the design lead and product owner ship code. No strict role boundaries during sprints.

## Key Quotes (synthesized, representative)

> "I'm so stoked about this project... thank you for delivering so fast." — leadership, after the site went live

> "This would basically make it so no one company can ever have the most powerful model, because it is always better when ensembled with others." — team member, describing the vision

> "The ability to claim SOTA will really add some juice... and say 'here's the place you can see the code / run it yourself.'" — leadership, on why provable SOTA matters

> "A non-coder set loose with Claude Code." — the design lead, on themselves

> "We all use the tool in our own CLI coding tools as our main daily driver. Fix what you don't like." — from the devplan

> "Everyone helps with everything and we all spend 9am to 2pm+ on a video call together context sharing and building each day." — from the devplan
