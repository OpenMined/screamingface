# Provenance of these icons

Vendored verbatim (unmodified, no recoloring) from
`OpenMined/screamingface-brand`'s `assets/model-logos/` — see that repo's per-provider
`source.txt` for original attribution. Copied here so `sf.connect()` can render a
real provider mark instead of a placeholder monogram.

| provider id (this SDK) | source folder | files |
|---|---|---|
| `anthropic` | `model-logos/anthropic` | `icon.svg` (light bg), `icon-dark.svg` (dark bg) |
| `openrouter` | `model-logos/openrouter` | `icon.svg` (light bg), `icon-dark.svg` (dark bg) |
| `ollama` | `model-logos/ollama` | `icon.svg` (light bg), `icon-dark.svg` (dark bg) |
| `huggingface` | `model-logos/huggingface` | `icon.svg` (full color, reads on both) |
| `gemini-cli` | `model-logos/google-gemini` | `icon.svg` (full color, reads on both) |

Only providers this SDK's Engine plugins actually support (see
`apps/aigateway/src/aigateway/plugins/*/plugin.py` `custom_llm_provider`) are vendored.
Any other provider id falls back to a neutral letter-monogram tile — never a redrawn
or recolored logo.

## Known gaps — deliberately on the monogram fallback

`codex` and `antigravity` are supported plugin providers with **no mark in
`screamingface-brand/assets/model-logos/`**, so they render the letter-monogram tile.
The same is true of Cloudflare, which backs the "Engine access" row (and is
infrastructure, not a model provider, so it would not live under `model-logos/`
anyway).

These are upstream gaps, not something to patch here: per `screamingface-brand`'s
`SYSTEM.md`, gaps hit while applying SFDS are reported against the brand repo so the
mark is sourced and vetted once, centrally. Do **not** substitute a different
company's mark (e.g. OpenAI's for `codex`) or hand-draw one — SFDS forbids
recolouring, redrawing, or substituting a provider logo.

If a new plugin provider is added, add its icon here the same way rather than
inventing a mark.
