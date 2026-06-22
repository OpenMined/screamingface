import { useState, type ReactNode } from 'react';
import { Play, Star, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useEvalRunsList } from '@/hooks/use-eval-runs';
import { useEvalRunActions } from '@/hooks/use-eval-run-actions';
import { EvalStatusBadge } from './EvalStatusBadge';
import { formatAccuracy, isUngradedDone } from './format';
import type { EvalRunSummary } from './types';
import type { RunPayload } from '@/components/run/types';

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRunLocally?: (payload: RunPayload) => void;
  /** Called after a bulk delete removes runs, so the parent can clear selection. */
  onBulkDeleted?: (deletedIds: string[]) => void;
}

// Which bulk action is pending confirmation. null = no dialog open.
type BulkMode = 'all' | 'non-starred';

interface RunsBodyProps {
  data: EvalRunSummary[];
  loading: boolean;
  error: Error | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onToggleFavorite: (run: EvalRunSummary) => void;
  onRunLocally?: (payload: RunPayload) => void;
}

// Loading / error / empty / list states for the runs panel body.
function RunsBody({
  data,
  loading,
  error,
  selectedId,
  onSelect,
  onToggleFavorite,
  onRunLocally,
}: RunsBodyProps): ReactNode {
  if (loading && data.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">Failed to load runs: {error.message}</div>;
  }
  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No evaluation runs yet.</p>
        <p className="text-xs">Use "New run" above, or the play button on a leaderboard entry.</p>
      </div>
    );
  }
  return (
    <>
      {data.map((run) => (
        <RunRow
          key={run.id}
          run={run}
          active={run.id === selectedId}
          onSelect={onSelect}
          onToggleFavorite={onToggleFavorite}
          onRunLocally={onRunLocally}
        />
      ))}
    </>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

interface RunRowProps {
  run: EvalRunSummary;
  active: boolean;
  onSelect: (id: string) => void;
  onToggleFavorite: (run: EvalRunSummary) => void;
  onRunLocally?: (payload: RunPayload) => void;
}

function RunRow({ run, active, onSelect, onToggleFavorite, onRunLocally }: RunRowProps) {
  return (
    <div
      onClick={() => onSelect(run.id)}
      className={cn(
        'cursor-pointer border-b border-border/50 px-6 py-3 transition-colors hover:bg-accent/40',
        active && 'bg-accent/60',
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-foreground">{run.spec_name}</div>
          <div className="text-xs text-muted-foreground">{formatTime(run.started_at)}</div>
        </div>
        {/* Right indicators on one line, vertically centered: pct, status, star, run. */}
        <div className="flex items-center gap-2 whitespace-nowrap">
          <span
            className="text-sm tabular-nums"
            title={isUngradedDone(run) ? 'Not graded — 0 checked questions' : undefined}
          >
            {formatAccuracy(run)}
          </span>
          <EvalStatusBadge status={run.status} />
          <button
            type="button"
            aria-label={run.favorite ? 'Unfavorite' : 'Favorite'}
            aria-pressed={run.favorite}
            title={run.favorite ? 'Unfavorite' : 'Favorite'}
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite(run);
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
  );
}

export function EvalRunsList({ selectedId, onSelect, onRunLocally, onBulkDeleted }: Props) {
  const { data, loading, error, refresh } = useEvalRunsList();
  const { toggleFavorite, deleteRun } = useEvalRunActions();
  const [bulkMode, setBulkMode] = useState<BulkMode | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const onToggleFavorite = async (run: EvalRunSummary): Promise<void> => {
    if (await toggleFavorite(run.id, !run.favorite)) await refresh(true);
  };

  const nonStarred = data.filter((run) => run.favorite === false);
  const hasRuns = data.length > 0;
  const hasNonStarred = nonStarred.length > 0;

  // Delete the targeted set sequentially (no bulk endpoint exists), then refresh
  // the list once. Selection is cleared by the parent via onBulkDeleted.
  const confirmBulkDelete = async (): Promise<void> => {
    const targets = bulkMode === 'non-starred' ? nonStarred : data;
    const ids = targets.map((run) => run.id);
    setBulkDeleting(true);
    const deleted: string[] = [];
    for (const id of ids) {
      if (await deleteRun(id)) deleted.push(id);
    }
    setBulkDeleting(false);
    setBulkMode(null);
    if (deleted.length > 0) {
      onBulkDeleted?.(deleted);
      await refresh(true);
    }
  };

  // Header with the bulk-clear controls. Always shown so the actions stay
  // discoverable; buttons disable when there's nothing to clear.
  const header = (
    <div className="flex items-center justify-end gap-2 border-b border-border px-6 py-2">
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground hover:text-destructive"
        disabled={!hasNonStarred}
        onClick={() => setBulkMode('non-starred')}
      >
        <Trash2 className="h-3.5 w-3.5" /> Clear non-starred
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground hover:text-destructive"
        disabled={!hasRuns}
        onClick={() => setBulkMode('all')}
      >
        <Trash2 className="h-3.5 w-3.5" /> Clear all
      </Button>
    </div>
  );

  const targetCount = bulkMode === 'non-starred' ? nonStarred.length : data.length;
  const noun = `run${targetCount === 1 ? '' : 's'}`;
  const confirmTitle = bulkMode === 'non-starred' ? 'Clear non-starred runs?' : 'Clear all runs?';
  const confirmMessage =
    bulkMode === 'non-starred'
      ? `${targetCount} non-starred ${noun} and their question results will be permanently removed. Starred runs are kept. This can't be undone.`
      : `All ${targetCount} ${noun} and their question results will be permanently removed. This can't be undone.`;

  return (
    <div className="flex flex-col">
      {header}
      <RunsBody
        data={data}
        loading={loading}
        error={error}
        selectedId={selectedId}
        onSelect={onSelect}
        onToggleFavorite={(r) => void onToggleFavorite(r)}
        onRunLocally={onRunLocally}
      />
      {bulkMode && (
        <ConfirmDialog
          title={confirmTitle}
          message={confirmMessage}
          confirmLabel={bulkDeleting ? 'Deleting…' : 'Delete'}
          destructive
          busy={bulkDeleting}
          onConfirm={() => void confirmBulkDelete()}
          onCancel={() => setBulkMode(null)}
        />
      )}
    </div>
  );
}
