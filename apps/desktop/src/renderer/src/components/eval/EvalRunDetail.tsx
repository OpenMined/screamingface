// apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx
import { useState } from 'react';
import { Upload, Play, Pencil } from 'lucide-react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useEvalRunDetail } from '@/hooks/use-eval-runs';
import { Url4Field } from '@/components/Url4Field';
import { Url4Editor } from '@/components/Url4Editor';
import { Button } from '@/components/ui/button';
import { EvalStatusBadge } from './EvalStatusBadge';
import { EvalQuestionsTable } from './EvalQuestionsTable';
import { PublishToLeaderboardDialog } from './PublishToLeaderboardDialog';
import type { RunPayload } from '@/components/run/types';

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

export function EvalRunDetail({
  runId,
  onRunLocally,
}: {
  runId: string;
  onRunLocally?: (payload: RunPayload) => void;
}) {
  const { info } = useServerStatus();
  const { data, loading, error } = useEvalRunDetail(runId);
  const [publishing, setPublishing] = useState(false);
  const [editing, setEditing] = useState(false);

  const serverUrl = info
    ? `${info.scheme}://${info.host === '0.0.0.0' ? 'localhost' : info.host}:${info.port}`
    : '';

  if (loading && !data) {
    return <div className="p-6 text-sm text-muted-foreground">Loading run…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">Failed: {error.message}</div>;
  }
  if (!data) return null;

  // Run (or re-run an edited expression) as a fresh run; the parent selects it.
  const triggerRun = (expression: string): void => {
    onRunLocally?.({ spec: data.spec_name, expression });
    setEditing(false);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <header className="border-b border-border px-6 py-4">
          <div className="mb-2 flex items-center gap-3">
            <h2 className="text-base font-semibold">{data.spec_name}</h2>
            <EvalStatusBadge status={data.status} />
            {data.status === 'done' && data.accuracy !== null && !!data.total_questions && (
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={() => setPublishing(true)}
              >
                <Upload className="h-3.5 w-3.5" /> Publish to Leaderboard
              </Button>
            )}
          </div>
          {editing ? (
            <div className="mb-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  Edit URL4 expression
                </span>
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
              <Url4Editor initial={data.url4_expression} serverUrl={serverUrl} onRun={triggerRun} />
            </div>
          ) : (
            <>
              <div className="mb-3 rounded border border-border bg-muted/30">
                <Url4Field value={data.url4_expression} serverUrl={serverUrl} readOnly />
              </div>
              {onRunLocally && (
                <div className="mb-3 flex items-center gap-2">
                  <Button
                    size="lg"
                    className="flex-1"
                    onClick={() => triggerRun(data.url4_expression)}
                  >
                    <Play className="h-4 w-4" /> Run Locally
                  </Button>
                  <Button variant="outline" size="lg" onClick={() => setEditing(true)}>
                    <Pencil className="h-4 w-4" /> Edit
                  </Button>
                </div>
              )}
            </>
          )}
          <dl className="grid grid-cols-4 gap-3 text-xs">
            <div>
              <dt className="text-muted-foreground">Accuracy</dt>
              <dd className="font-medium tabular-nums">{formatPercent(data.accuracy)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Correct / Total</dt>
              <dd className="font-medium tabular-nums">
                {data.correct_questions ?? 0} / {data.total_questions ?? 0}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Started</dt>
              <dd className="tabular-nums">{formatTime(data.started_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Finished</dt>
              <dd className="tabular-nums">{formatTime(data.finished_at)}</dd>
            </div>
          </dl>
          {data.error && (
            <div className="mt-3 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {data.error}
            </div>
          )}
        </header>
        <EvalQuestionsTable questions={data.questions} />
      </div>
      {publishing && (
        <PublishToLeaderboardDialog
          run={data}
          serverUrl={serverUrl}
          onClose={() => setPublishing(false)}
        />
      )}
    </div>
  );
}
