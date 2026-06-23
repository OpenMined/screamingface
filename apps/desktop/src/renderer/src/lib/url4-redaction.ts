// apps/desktop/src/renderer/src/lib/url4-redaction.ts
//
// Pure helpers for the "Publish to Leaderboard" flow (SF-181 / D-SCORE-006).
//
// A published url4 expression is documentation that others may try to run. When
// it references `/data/<ref>` blobs, those are content-addressed inline data that
// live only on the submitter's local server — they will NOT resolve on anyone
// else's machine and may leak local code/data. We detect those refs so the
// publish dialog can warn and optionally redact them. (Note: `/data/<ref>` is a
// content-hash blob reference, not a "private spec" — there is no public/private
// spec concept in the codebase.)
//
// Also parses spec_name into benchmark/spec ids and derives the providers a run
// used from the expression. All functions are pure and dependency-free.

const DATA_REF_RE = /\/data\/[A-Za-z0-9_./-]+/g;
const REDACTED_REF = '/data/<redacted>';
const KNOWN_PROVIDERS = ['claude', 'codex', 'gemini', 'antigravity', 'ollama'] as const;

/** Every `/data/<ref>` segment in the expression (empty array if none). */
export function findLocalDataRefs(expression: string): string[] {
  if (!expression) return [];
  return expression.match(DATA_REF_RE) ?? [];
}

/** True when the expression references at least one local-only `/data` blob. */
export function hasLocalDataRefs(expression: string): boolean {
  return findLocalDataRefs(expression).length > 0;
}

/** Replace every `/data/<ref>` with `/data/<redacted>` (still readable, not runnable). */
export function sanitizeDataRefs(expression: string): string {
  if (!expression) return expression;
  return expression.replace(DATA_REF_RE, REDACTED_REF);
}

export interface ParsedSpecName {
  /** Non-null only when spec_name carries the `<benchmark>:<spec>` convention. */
  benchmark_id: string | null;
  spec_id: string;
}

/**
 * Split `spec_name` on the first colon into `<benchmark_id>:<spec_id>`. When there
 * is no colon (today's common case), benchmark_id is null and the caller must
 * collect it from the user; spec_id defaults to the whole name.
 */
export function parseSpecName(specName: string): ParsedSpecName {
  const idx = specName.indexOf(':');
  if (idx === -1) {
    return { benchmark_id: null, spec_id: specName };
  }
  const benchmark = specName.slice(0, idx);
  return {
    benchmark_id: benchmark.length > 0 ? benchmark : null,
    spec_id: specName.slice(idx + 1),
  };
}

/**
 * Providers referenced by the url4 expression, in a stable order. Heuristic token
 * scan over the known provider names — the dialog shows the result and lets the
 * user edit it, so a miss is recoverable rather than silently wrong.
 */
export function deriveProviders(expression: string): string[] {
  if (!expression) return [];
  const lower = expression.toLowerCase();
  return KNOWN_PROVIDERS.filter((provider) => lower.includes(provider));
}
