// apps/desktop/src/renderer/src/lib/publish-guard.ts
//
// Deterministic, client-checkable reasons a run cannot be published — a preflight
// mirror of the scoreboard ScoreSubmission validators we can evaluate without a
// round-trip (apps/scoreboard/src/scoreboard/scores/schemas.py). Lets the publish
// dialog block + explain up front instead of bouncing the user off a 422.

import type { EvalRunDetail } from '@/components/eval/types';

export interface PublishGuardInput {
  run: EvalRunDetail;
  /** The expression that will actually be published (post-sanitization). */
  url4Expression: string;
}

/**
 * Returns a user-facing reason the run can't be published, or null if it clears
 * the deterministic checks. `accuracy` is recomputed server-side from the totals,
 * so it can't be out of range once `total > 0` — no check needed here.
 */
export function publishBlockReason({ run, url4Expression }: PublishGuardInput): string | null {
  const total = run.total_questions ?? 0;
  const correct = run.correct_questions ?? 0;

  if (total <= 0) {
    return 'This run has no graded questions, so there is nothing to publish. Run an eval that produces scored results first (a degraded run from a backend outage scores zero rows).';
  }
  if (correct > total) {
    return `This run's totals are inconsistent (correct ${correct} exceeds total ${total}), so the scoreboard would reject it.`;
  }
  if (url4Expression.trim().length === 0) {
    return 'This run has no URL4 expression to publish.';
  }
  return null;
}
