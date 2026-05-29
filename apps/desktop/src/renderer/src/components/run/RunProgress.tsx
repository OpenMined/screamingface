import type { EvalRunDetail } from '@/components/eval/types';

export function RunProgress({ run }: { run: EvalRunDetail | null }) {
  if (!run) return null;
  if (run.total_questions == null || run.correct_questions == null) {
    return <div className="text-sm text-muted-foreground">Starting run…</div>;
  }
  const pct = run.accuracy != null ? ` · accuracy ${(run.accuracy * 100).toFixed(1)}%` : '';
  return (
    <div className="text-sm text-muted-foreground" role="status">
      {run.correct_questions} / {run.total_questions}
      {pct}
    </div>
  );
}
