// apps/desktop/src/main/services/fetch-leaderboard.ts
//
// Fetches the ranked leaderboard for one benchmark from the public scoreboard
// (GET /v1/leaderboard/{benchmark_id}) from the MAIN process, so the request is
// exempt from renderer CORS (same rationale as list-benchmarks/publish-score,
// SF-273).
//
// Returns null on ANY failure (unreachable, non-2xx incl. unknown-benchmark 404,
// bad body) — this milestone has no consumer yet, so there is no need for
// status-specific error surfacing; a later milestone's renderer hook can treat
// "couldn't load" as a single state.
//
// OME-321, milestone 1: this function is intentionally unwired — no IPC channel,
// no preload exposure, no UI. It only proves the fetch/mapping/error-handling
// logic in isolation ahead of later milestones that make it reachable.

import { resolvePublishContext } from './publish-context';
import { publishLog } from './publish-log';

const TIMEOUT_MS = 8_000;

export interface LeaderboardBenchmark {
  id: string;
  displayName: string;
  description: string | null;
  datasetUrl: string | null;
}

export interface LeaderboardEntry {
  rank: number;
  specId: string;
  accuracy: number;
  totalQuestions: number;
  ranWithProviders: string[];
  submittedAt: string;
  submittedBy: string | null;
  verifiedByOpenmined: boolean;
  url4Expression: string;
}

export interface LeaderboardData {
  benchmark: LeaderboardBenchmark;
  entries: LeaderboardEntry[];
}

interface BenchmarkResponseBody {
  id?: unknown;
  display_name?: unknown;
  description?: unknown;
  dataset_url?: unknown;
}

interface LeaderboardEntryResponseBody {
  rank?: unknown;
  spec_id?: unknown;
  accuracy?: unknown;
  total_questions?: unknown;
  ran_with_providers?: unknown;
  submitted_at?: unknown;
  submitted_by?: unknown;
  verified_by_openmined?: unknown;
  url4_expression?: unknown;
}

interface LeaderboardResponseBody {
  benchmark?: BenchmarkResponseBody;
  entries?: unknown[];
}

function mapBenchmark(b: BenchmarkResponseBody | undefined): LeaderboardBenchmark | null {
  if (typeof b?.id !== 'string' || b.id.length === 0) return null;
  return {
    id: b.id,
    displayName:
      typeof b.display_name === 'string' && b.display_name.length > 0 ? b.display_name : b.id,
    description: typeof b.description === 'string' ? b.description : null,
    datasetUrl: typeof b.dataset_url === 'string' ? b.dataset_url : null,
  };
}

function mapEntry(e: unknown): LeaderboardEntry | null {
  const row = e as LeaderboardEntryResponseBody;
  if (
    typeof row?.rank !== 'number' ||
    typeof row.spec_id !== 'string' ||
    row.spec_id.length === 0 ||
    typeof row.accuracy !== 'number' ||
    typeof row.total_questions !== 'number' ||
    !Array.isArray(row.ran_with_providers) ||
    typeof row.submitted_at !== 'string' ||
    typeof row.verified_by_openmined !== 'boolean' ||
    typeof row.url4_expression !== 'string'
  ) {
    return null;
  }
  return {
    rank: row.rank,
    specId: row.spec_id,
    accuracy: row.accuracy,
    totalQuestions: row.total_questions,
    ranWithProviders: row.ran_with_providers.filter((p): p is string => typeof p === 'string'),
    submittedAt: row.submitted_at,
    submittedBy: typeof row.submitted_by === 'string' ? row.submitted_by : null,
    verifiedByOpenmined: row.verified_by_openmined,
    url4Expression: row.url4_expression,
  };
}

/**
 * Fetch the ranked leaderboard for a benchmark. Returns null if the benchmark
 * is unknown (404), the scoreboard is unreachable, or the response is malformed.
 */
export async function listLeaderboard(
  benchmarkId: string,
  top?: number,
): Promise<LeaderboardData | null> {
  const ctx = resolvePublishContext();
  const base = `${ctx.scoreboardUrl.replace(/\/$/, '')}/v1/leaderboard/${encodeURIComponent(benchmarkId)}`;
  const url = typeof top === 'number' ? `${base}?top=${top}` : base;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      publishLog(`leaderboard: GET ${url} -> HTTP ${res.status}`);
      return null;
    }
    const data = (await res.json()) as LeaderboardResponseBody;
    const benchmark = mapBenchmark(data.benchmark);
    if (benchmark === null) {
      publishLog(`leaderboard: GET ${url} -> malformed benchmark in response body`);
      return null;
    }
    const entries = Array.isArray(data.entries)
      ? data.entries.map(mapEntry).filter((e): e is LeaderboardEntry => e !== null)
      : [];
    return { benchmark, entries };
  } catch (e) {
    publishLog(`leaderboard: GET ${url} failed: ${(e as Error).message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
