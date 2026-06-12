// apps/desktop/src/main/services/publish-score.ts
//
// Publishes a local eval_run aggregate to the public scoreboard (SF-181 /
// D-SCORE-006) from the MAIN process, so the request is exempt from renderer
// CORS (SF-273): the scoreboard need not allowlist the desktop app origin
// (localhost in dev, file://null when packaged). Builds the exact wire shape the
// scoreboard accepts (nested `client`, see apps/scoreboard/tests/unit/
// test_sf_payload.py), POSTs it with an Idempotency-Key so repeat clicks don't
// duplicate, and retries transient failures. The contract is strict
// (`extra="forbid"`) — send these keys only.

import { resolvePublishContext } from './publish-context';
import type { PublishOutcome, PublishResult, PublishScoreRequest } from '../../preload/types';

const TIMEOUT_MS = 10_000;
const BACKOFF_MS = [1_000, 2_000, 4_000];

interface ScoreResponse {
  id: string;
  benchmark_id: string;
  spec_id: string;
}

/** Map a non-2xx status to actionable copy. */
function errorForStatus(status: number, body: string): string {
  switch (status) {
    case 404:
      return 'That benchmark is not registered on the scoreboard yet. Coordinate with the scoreboard owner before publishing.';
    case 400:
      return 'The scoreboard rejected the aggregate (accuracy must equal correct/total). This run may have inconsistent totals.';
    case 422:
      return 'The submission did not match the scoreboard contract. This is a bug — please report it.';
    default:
      return `Scoreboard returned HTTP ${status}: ${body.slice(0, 200)}`;
  }
}

function buildBody(
  request: PublishScoreRequest,
  client: { name: string; version: string; platform: string },
): Record<string, unknown> {
  const total = request.totalQuestions ?? 0;
  const correct = request.correctQuestions ?? 0;
  // Recompute accuracy from the integer totals: the scoreboard 400s if `accuracy`
  // differs from correct/total by >0.01, so never trust a stored rounded value.
  const accuracy = total > 0 ? correct / total : 0;
  const submittedBy =
    request.submittedBy && request.submittedBy.trim().length > 0
      ? request.submittedBy.trim()
      : null;
  return {
    version: 1,
    benchmark_id: request.benchmarkId,
    spec_id: request.specId,
    url4_expression: request.url4Expression,
    submitted_by: submittedBy,
    accuracy,
    total_questions: total,
    correct_questions: correct,
    ran_with_providers: request.providers,
    ran_at_local: request.ranAtLocal,
    client: { name: client.name, version: client.version, platform: client.platform },
    metadata: null,
  };
}

async function postOnce(
  url: string,
  body: Record<string, unknown>,
  idempotencyKey: string,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(`${url.replace(/\/$/, '')}/v1/scores`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * POST the score to the scoreboard with retries. Returns a discriminated
 * outcome rather than throwing, so the IPC layer can pass it straight to the
 * renderer's UI state machine.
 */
export async function submitScore(request: PublishScoreRequest): Promise<PublishOutcome> {
  const ctx = resolvePublishContext();
  const body = buildBody(request, ctx.client);
  const idempotencyKey = request.runId;

  let lastErr: string | null = null;
  // 1 initial attempt + up to 3 retries on transient failures.
  for (let attempt = 0; attempt <= BACKOFF_MS.length; attempt += 1) {
    if (attempt > 0) await sleep(BACKOFF_MS[attempt - 1]);
    let res: Response;
    try {
      res = await postOnce(ctx.scoreboardUrl, body, idempotencyKey);
    } catch {
      lastErr = 'Could not reach the scoreboard. Check your connection and try again.';
      continue; // network/abort — retry
    }
    if (res.ok) {
      const data = (await res.json()) as ScoreResponse;
      const portalLink = `${ctx.portalUrl.replace(/\/$/, '')}/spec.html?benchmark=${encodeURIComponent(data.benchmark_id)}&spec=${encodeURIComponent(data.spec_id)}`;
      const value: PublishResult = {
        id: data.id,
        benchmarkId: data.benchmark_id,
        specId: data.spec_id,
        portalLink,
      };
      return { ok: true, value };
    }
    if (res.status >= 500) {
      lastErr = errorForStatus(res.status, await res.text());
      continue; // server error — retry
    }
    // 4xx (other than 5xx) is deterministic — do not retry.
    return { ok: false, error: errorForStatus(res.status, await res.text()) };
  }
  return { ok: false, error: lastErr ?? 'Publishing failed after several attempts.' };
}
