// apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx
import { cn } from '@/lib/utils';
import { useEvalRunsList } from '@/hooks/use-eval-runs';
import { EvalStatusBadge } from './EvalStatusBadge';
import type { EvalRunSummary } from './types';
import type { RunPayload } from '@/components/run/types';

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRunLocally?: (payload: RunPayload) => void;
}

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function EvalRunsList({ selectedId, onSelect, onRunLocally }: Props) {
  const { data, loading, error } = useEvalRunsList();

  if (loading && data.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">Failed to load runs: {error.message}</div>;
  }
  if (data.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No evaluation runs yet.</p>
        <p className="text-xs">Click a leaderboard entry's "Run Locally" link to start one.</p>
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="sticky top-0 bg-background text-xs text-muted-foreground">
        <tr className="border-b border-border">
          <th className="px-3 py-2 text-left font-medium">Started</th>
          <th className="px-3 py-2 text-left font-medium">Spec</th>
          <th className="px-3 py-2 text-left font-medium">Status</th>
          <th className="px-3 py-2 text-right font-medium">Accuracy</th>
          <th className="px-3 py-2 text-right font-medium">Correct / Total</th>
          <th className="px-3 py-2 text-left font-medium"></th>
        </tr>
      </thead>
      <tbody>
        {data.map((run: EvalRunSummary) => {
          const active = run.id === selectedId;
          return (
            <tr
              key={run.id}
              onClick={() => onSelect(run.id)}
              className={cn(
                'cursor-pointer border-b border-border/50 transition-colors hover:bg-accent/40',
                active && 'bg-accent/60',
              )}
            >
              <td className="px-3 py-2 text-xs">{formatTime(run.started_at)}</td>
              <td className="px-3 py-2">{run.spec_name}</td>
              <td className="px-3 py-2">
                <EvalStatusBadge status={run.status} />
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{formatPercent(run.accuracy)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground">
                {run.correct_questions ?? 0} / {run.total_questions ?? 0}
              </td>
              <td className="px-3 py-2 text-left">
                {onRunLocally && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRunLocally({ spec: run.spec_name, expression: run.url4_expression });
                    }}
                    className="text-xs text-primary underline"
                  >
                    Run Locally
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
