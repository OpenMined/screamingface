// apps/desktop/src/renderer/src/hooks/use-publish-score.ts
//
// Publishes a local eval_run aggregate to the public scoreboard (SF-181 /
// D-SCORE-006). Builds the exact wire shape the scoreboard accepts (nested
// `client`, see apps/scoreboard/tests/unit/test_sf_payload.py), POSTs it with
// an Idempotency-Key so repeat clicks don't duplicate, and retries transient
// failures. The contract is strict (`extra="forbid"`) — send these keys only.

import { useCallback, useState } from 'react';
import type { EvalRunDetail } from '@/components/eval/types';

const TIMEOUT_MS = 10_000;
const BACKOFF_MS = [1_000, 2_000, 4_000];

export type PublishStatus = 'idle' | 'submitting' | 'success' | 'error';

export interface PublishInputs {
  run: EvalRunDetail;
  benchmarkId: string;
  specId: string;
  /** url4 expression to publish — already sanitized if the user chose to. */
  url4Expression: string;
  providers: string[];
  /** null/empty → anonymous. */
  submittedBy: string | null;
}

export interface PublishResult {
  id: string;
  benchmarkId: string;
  specId: string;
  /** Deep link to the leaderboard entry. */
  portalLink: string;
}

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
  inputs: PublishInputs,
  client: { name: string; version: string; platform: string },
): Record<string, unknown> {
  const { run } = inputs;
  const total = run.total_questions ?? 0;
  const correct = run.correct_questions ?? 0;
  // Recompute accuracy from the integer totals: the scoreboard 400s if `accuracy`
  // differs from correct/total by >0.01, so never trust a stored rounded value.
  const accuracy = total > 0 ? correct / total : 0;
  const submittedBy =
    inputs.submittedBy && inputs.submittedBy.trim().length > 0 ? inputs.submittedBy.trim() : null;
  return {
    version: 1,
    benchmark_id: inputs.benchmarkId,
    spec_id: inputs.specId,
    url4_expression: inputs.url4Expression,
    submitted_by: submittedBy,
    accuracy,
    total_questions: total,
    correct_questions: correct,
    ran_with_providers: inputs.providers,
    ran_at_local: run.finished_at ?? run.started_at,
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

export function usePublishScore() {
  const [status, setStatus] = useState<PublishStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PublishResult | null>(null);

  const publish = useCallback(async (inputs: PublishInputs): Promise<PublishResult | null> => {
    setStatus('submitting');
    setError(null);
    try {
      const ctx = await window.electronAPI.publish.getContext();
      const body = buildBody(inputs, ctx.client);
      const idempotencyKey = inputs.run.id;

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
          const out: PublishResult = {
            id: data.id,
            benchmarkId: data.benchmark_id,
            specId: data.spec_id,
            portalLink,
          };
          setResult(out);
          setStatus('success');
          return out;
        }
        if (res.status >= 500) {
          lastErr = errorForStatus(res.status, await res.text());
          continue; // server error — retry
        }
        // 4xx (other than 5xx) is deterministic — do not retry.
        const errText = errorForStatus(res.status, await res.text());
        setError(errText);
        setStatus('error');
        return null;
      }
      setError(lastErr ?? 'Publishing failed after several attempts.');
      setStatus('error');
      return null;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  return { publish, status, error, result };
}
