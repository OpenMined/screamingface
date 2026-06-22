// apps/desktop/src/main/services/list-benchmarks.ts
//
// Fetches the canonical set of benchmarks registered on the public scoreboard
// (GET /v1/benchmarks) from the MAIN process, so the request is exempt from
// renderer CORS (same rationale as publish-score, SF-273). Used for pre-flight
// validation of the SF-300 auto-derived benchmark id: the publish dialog warns
// when the derived id isn't registered (publish itself hard-404s unknown ids).
//
// Returns null on ANY failure (unreachable, non-2xx, bad body) so the renderer
// can treat "registry unavailable" distinctly from "benchmark not registered"
// and never show a false "unknown benchmark" warning.

import { resolvePublishContext } from './publish-context';
import { publishLog } from './publish-log';
import type { KnownBenchmark } from '../../preload/types';

const TIMEOUT_MS = 8_000;

interface BenchmarksResponseBody {
  benchmarks?: Array<{ id?: unknown; display_name?: unknown }>;
}

export async function listBenchmarks(): Promise<KnownBenchmark[] | null> {
  const ctx = resolvePublishContext();
  const url = `${ctx.scoreboardUrl.replace(/\/$/, '')}/v1/benchmarks`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      publishLog(`benchmarks: GET ${url} -> HTTP ${res.status}`);
      return null;
    }
    const data = (await res.json()) as BenchmarksResponseBody;
    const rows = Array.isArray(data.benchmarks) ? data.benchmarks : [];
    return rows
      .filter(
        (b): b is { id: string; display_name?: unknown } =>
          typeof b?.id === 'string' && b.id.length > 0,
      )
      .map((b) => ({
        id: b.id,
        displayName:
          typeof b.display_name === 'string' && b.display_name.length > 0 ? b.display_name : b.id,
      }));
  } catch (e) {
    publishLog(`benchmarks: GET ${url} failed: ${(e as Error).message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
