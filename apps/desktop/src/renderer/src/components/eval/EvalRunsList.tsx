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
    <div className="flex flex-col">
      {data.map((run: EvalRunSummary) => {
        const active = run.id === selectedId;
        return (
          <div
            key={run.id}
            onClick={() => onSelect(run.id)}
            className={cn(
              'cursor-pointer border-b border-border/50 px-3 py-3 transition-colors hover:bg-accent/40',
              active && 'bg-accent/60',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-foreground">{run.spec_name}</div>
                <div className="text-xs text-muted-foreground">{formatTime(run.started_at)}</div>
              </div>
              <div className="flex items-center gap-2 whitespace-nowrap">
                <EvalStatusBadge status={run.status} />
                <div className="text-right text-sm tabular-nums">{formatPercent(run.accuracy)}</div>
                {onRunLocally && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRunLocally({ spec: run.spec_name, expression: run.url4_expression });
                    }}
                    className="whitespace-nowrap text-xs text-primary underline"
                  >
                    Run Locally
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
