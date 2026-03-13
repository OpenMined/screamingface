# Web Package — Developer Context

## This Package
Static marketing website for the AI ensemble product. Built with Next.js 16, React 19, Tailwind CSS v4, Recharts, and shadcn/ui. Deployed to GitHub Pages at screamingface.ai.

## Developer Notes
- Frontend dev with strong HTML/CSS/design background, newer to React
- Explain React component structure and state clearly when relevant
- Strong on layout, spacing, and CSS — trust instincts there
- Build one screen/component at a time
- Always use Tailwind for styling unless told otherwise
- Keep component files small and focused
- Care about data visualization quality — suggest D3 approaches when charting comes up
- When in doubt, match existing patterns in the codebase rather than introducing new ones

## Personas & Audience Targeting

This site serves multiple audiences on different pages. Always check the weighting guide before writing copy or making design decisions: `personas/weighting-guide.md`

**Quick reference for this package:**

| Page | Primary Audience | Secondary | Reference |
|------|-----------------|-----------|-----------|
| Homepage (/) | Audience 1 — technical developers, benchmark enthusiasts | Audience 2 | — |
| /why page | Audience 2 — thought leaders, journalists, policy champions | — | ABC + Time 100 reports |
| General copy/design | Audience 1 | Audience 2 | — |

- **Audience 1** wants evidence, not adjectives. Benchmark numbers, install commands, open methodology. They close tabs on marketing BS. → `personas/persona-audience-1.md`
- **Audience 2** wants societal framing, not technical detail. The 2-year window, public infrastructure, coalition. They need a different tone than the homepage. → `personas/persona-audience-2.md`
- **ABC and Time 100 cohorts** are reference material for the /why page and any outreach/positioning work. Read the group reports, not individual files, unless targeting specific people.

If you're working on copy or design and the audience isn't obvious from the page, ask which audience to target.
