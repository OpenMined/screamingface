// apps/desktop/src/renderer/src/components/eval/format.ts
//
// Shared eval-run formatting. A finished run that recorded zero checked
// questions (an inference-only spec with no check_correct grading node) is NOT
// an accuracy result — showing "0.0%" reads as "0% correct". Treat it as
// "not graded" instead.
import type { EvalRunStatus } from './types';

interface RunLike {
  status: EvalRunStatus;
  accuracy: number | null;
  total_questions: number | null;
}

/** True when the run recorded at least one checked question. */
export function isGradedRun(run: RunLike): boolean {
  return (run.total_questions ?? 0) > 0;
}

/** A finished run that graded nothing — i.e. the spec had no check step. */
export function isUngradedDone(run: RunLike): boolean {
  return run.status === 'done' && !isGradedRun(run);
}

/** Accuracy label: a percentage when graded, "—" when not graded / incomplete. */
export function formatAccuracy(run: RunLike): string {
  if (!isGradedRun(run) || run.accuracy === null) return '—';
  return `${(run.accuracy * 100).toFixed(1)}%`;
}
