import { Play, Star } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEvalRunsList } from '@/hooks/use-eval-runs';
import { useEvalRunActions } from '@/hooks/use-eval-run-actions';
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
  const { data, loading, error, refresh } = useEvalRunsList();
  const { toggleFavorite } = useEvalRunActions();

  const onToggleFavorite = async (run: EvalRunSummary): Promise<void> => {
    if (await toggleFavorite(run.id, !run.favorite)) await refresh(true);
  };

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
        <p className="text-xs">Use "New run" above, or the play button on a leaderboard entry.</p>
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
              'cursor-pointer border-b border-border/50 px-6 py-3 transition-colors hover:bg-accent/40',
              active && 'bg-accent/60',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-foreground">{run.spec_name}</div>
                <div className="text-xs text-muted-foreground">{formatTime(run.started_at)}</div>
              </div>
              {/* Right indicators: top row = percent + status, bottom row = star + run. */}
              <div className="flex flex-col items-end gap-1 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  <span className="text-sm tabular-nums">{formatPercent(run.accuracy)}</span>
                  <EvalStatusBadge status={run.status} />
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label={run.favorite ? 'Unfavorite' : 'Favorite'}
                    aria-pressed={run.favorite}
                    title={run.favorite ? 'Unfavorite' : 'Favorite'}
                    onClick={(e) => {
                      e.stopPropagation();
                      void onToggleFavorite(run);
                    }}
                    className={cn(
                      'rounded p-1 transition-colors hover:bg-accent',
                      run.favorite ? 'text-chart-5' : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <Star className={cn('h-4 w-4', run.favorite && 'fill-current')} />
                  </button>
                  {onRunLocally && (
                    <button
                      type="button"
                      aria-label="Run locally"
                      title="Run locally"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRunLocally({ spec: run.spec_name, expression: run.url4_expression });
                      }}
                      className="rounded p-1 text-primary transition-colors hover:bg-primary/10"
                    >
                      <Play className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
