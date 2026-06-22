// apps/desktop/src/renderer/src/lib/benchmark-identity.ts
//
// Auto-derives a benchmark *identity* for the "Publish to Leaderboard" flow
// (SF-300), replacing the old free-text Benchmark-ID input. An identity has
// three parts, all derived — never typed by the user:
//
//   1. datasetFilename — the `*.eval.jsonl` (or .jsonl/.json/.csv) file the run's
//      url4 expression iterated over, pulled from the dataset/collection source URL.
//   2. id             — a stable, slugified benchmark id derived from that filename
//      (e.g. `honest-agi-live-week-3.eval.jsonl` -> `honest-agi-live-week-3`).
//   3. signature      — a SHA-256 content hash that pins the id to the exact eval
//      content the run executed against, so an id can't silently drift onto a
//      different dataset.
//
// CLIENT-SIDE GAP (documented, intentional): the desktop app does NOT hold the
// raw jsonl bytes the server fetched — an eval_run only persists the per-question
// `question`/`expected` pairs (see eval/types.ts) and the url4 expression. So the
// signature here is computed over a *normalized reconstruction* of those rows,
// not the original file bytes. It is stable and collision-resistant for our
// purposes (detecting "same id, different content"), but it is NOT byte-identical
// to a hash the scoreboard would compute over the source file.
//
// SERVER FOLLOW-UP (out of scope for this client ticket — see PR body): the
// authoritative fix is for the server to (a) embed a non-editable benchmark-ID
// metadata field into each dataset row, and (b) record/verify a hash of the
// fetched source bytes, so the scoreboard can verify id<->signature against the
// real file rather than this client reconstruction.

import type { EvalRunDetail } from '@/components/eval/types';

/** Matches a dataset/collection source filename ending in a known eval extension. */
const DATASET_FILE_RE = /([A-Za-z0-9._-]+\.(?:eval\.jsonl|jsonl|json|csv))(?=$|[)\s*!,;])/i;
/** Strips the trailing dataset extension to leave the benchmark stem. */
const EXT_STRIP_RE = /\.(?:eval\.jsonl|jsonl|json|csv)$/i;

export interface BenchmarkIdentity {
  /** Slugified, stable benchmark id derived from the dataset filename. */
  id: string;
  /** Human label (e.g. "Honest AGI Live week 3") when the filename matches a known pattern, else a titleized stem. */
  label: string;
  /** The dataset filename detected in the url4 expression, or null when none found. */
  datasetFilename: string | null;
  /** SHA-256 over the normalized reconstructed eval content (hex). Empty when no content. */
  signature: string;
}

/**
 * Pull the dataset filename out of a url4 expression. We look for the last path
 * segment of a dataset/collection source URL ending in a known eval extension.
 * Returns null when the expression has no recognizable dataset file (e.g. an
 * inline `/data/<hash>` blob run, or a single-prompt run).
 */
export function detectDatasetFilename(expression: string): string | null {
  if (!expression) return null;
  // Scan all matches and take the last dataset-like filename: the collection
  // source is typically the left operand of `*`, but reducers/checks may name
  // other files — the dataset is the one carrying an eval extension. We prefer
  // the first `.eval.jsonl` match, else the first match of any kind.
  const all = expression.match(new RegExp(DATASET_FILE_RE, 'gi')) ?? [];
  if (all.length === 0) return null;
  const evalJsonl = all.find((f) => /\.eval\.jsonl$/i.test(f));
  return evalJsonl ?? all[0];
}

/**
 * Slugify a dataset filename into a stable benchmark id: strip the extension,
 * lowercase, and collapse non-alphanumeric runs to single hyphens.
 */
export function deriveBenchmarkId(filename: string): string {
  const stem = filename.replace(EXT_STRIP_RE, '');
  return stem
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Human-readable label for a benchmark id. Recognizes the "honest-agi-live-week-N"
 * family and renders it as "Honest AGI Live week N"; otherwise titleizes the slug.
 */
export function deriveBenchmarkLabel(id: string): string {
  const week = id.match(/^honest-agi-live-week-(\d+)$/i);
  if (week) return `Honest AGI Live week ${week[1]}`;
  if (/^honest-agi-live$/i.test(id)) return 'Honest AGI Live';
  if (!id) return '';
  return id
    .split('-')
    .filter(Boolean)
    .map((word) => {
      // Keep all-caps acronyms (agi -> AGI, hle -> HLE) uppercased when short.
      if (/^[a-z]{2,4}$/.test(word) && /^(agi|hle|gpqa|mmlu|swe)$/i.test(word)) {
        return word.toUpperCase();
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
}

/**
 * Normalize the run's graded questions into stable jsonl bytes for hashing:
 * one `{question, expected}` object per row, ordered by `idx`, NFC-normalized,
 * newline-joined. This is the reconstruction the signature is computed over (see
 * the CLIENT-SIDE GAP note at the top of this file).
 */
export function normalizeEvalContent(run: EvalRunDetail): string {
  const rows = [...run.questions]
    .sort((a, b) => a.idx - b.idx)
    .map((q) => JSON.stringify({ question: q.question, expected: q.expected }).normalize('NFC'));
  return rows.join('\n');
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * SHA-256 (hex) over the normalized eval content. Returns '' for empty content
 * so callers can treat "no content to sign" distinctly from a real digest.
 */
export async function computeContentSignature(run: EvalRunDetail): Promise<string> {
  const content = normalizeEvalContent(run);
  if (content.length === 0) return '';
  const bytes = new TextEncoder().encode(content);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return toHex(digest);
}

/**
 * Derive the full benchmark identity (id + label + filename + signature) for a
 * run. Async because the signature is a Web Crypto digest.
 */
export async function deriveBenchmarkIdentity(run: EvalRunDetail): Promise<BenchmarkIdentity> {
  const datasetFilename = detectDatasetFilename(run.url4_expression);
  // Fall back to the run's spec_name stem when the expression has no dataset
  // file (inline blob / single-prompt runs) so the id is never empty when a
  // spec name exists. The signature still pins it to the executed content.
  const baseName = datasetFilename ?? run.spec_name;
  const id = deriveBenchmarkId(baseName);
  const label = deriveBenchmarkLabel(id);
  const signature = await computeContentSignature(run);
  return { id, label, datasetFilename, signature };
}

export interface IdentityConsistency {
  ok: boolean;
  /** User-facing reason when not ok; null when consistent. */
  reason: string | null;
}

/**
 * Verify a derived id<->signature pair is internally consistent before publish.
 * Blocks when the id is empty (nothing to attribute the score to) or the
 * signature is missing (no graded content to pin the id to — i.e. the id can't
 * be trusted to describe what actually ran).
 */
export function verifyIdentityConsistency(identity: BenchmarkIdentity): IdentityConsistency {
  if (!identity.id) {
    return {
      ok: false,
      reason:
        'Could not derive a benchmark ID from this run (no dataset filename in the URL4 expression and no spec name). This run can’t be attributed to a leaderboard benchmark.',
    };
  }
  if (!identity.signature) {
    return {
      ok: false,
      reason:
        'This run has no graded content to sign, so its benchmark ID can’t be verified against what it ran. Re-run the eval against the dataset before publishing.',
    };
  }
  return { ok: true, reason: null };
}
