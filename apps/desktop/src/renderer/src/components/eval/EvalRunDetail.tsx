// apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx
import { useState, lazy, Suspense } from 'react';
import { Upload, Play, Pencil, Trash2, Save } from 'lucide-react';
import type { OnMount } from '@monaco-editor/react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useEvalRunDetail } from '@/hooks/use-eval-runs';
import { useEvalRunActions } from '@/hooks/use-eval-run-actions';
import { registerUrl4Language } from '@/lib/url4-language';
import { Url4Field } from '@/components/Url4Field';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EvalStatusBadge } from './EvalStatusBadge';
import { EvalQuestionsTable } from './EvalQuestionsTable';
import { PublishToLeaderboardDialog } from './PublishToLeaderboardDialog';
import { formatAccuracy, isUngradedDone } from './format';
import type { RunPayload } from '@/components/run/types';

// Lazy so the heavy monaco bundle only loads when the editor popup opens.
const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

// Register the url4 language on the popup's monaco instance and apply it to the model.
const mountUrl4Editor: OnMount = (editor, monaco) => {
  registerUrl4Language(monaco);
  const model = editor.getModel();
  if (model) monaco.editor.setModelLanguage(model, 'url4');
};

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

export function EvalRunDetail({
  runId,
  onRunLocally,
  onDeleted,
}: {
  runId: string;
  onRunLocally?: (payload: RunPayload) => void;
  onDeleted?: () => void;
}) {
  const { info } = useServerStatus();
  const { data, loading, error, refresh } = useEvalRunDetail(runId);
  const { deleteRun, saveExpression } = useEvalRunActions();
  const [publishing, setPublishing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  // Persist an edited expression onto this run, then refetch so the panel updates.
  const handleSaveExpression = async (expression: string): Promise<void> => {
    if (await saveExpression(runId, expression)) await refresh();
  };

  const confirmDelete = async (): Promise<void> => {
    setDeleting(true);
    const ok = await deleteRun(runId);
    setDeleting(false);
    setConfirmingDelete(false);
    if (ok) onDeleted?.();
  };

  return (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div className="min-w-0 flex-1 overflow-y-auto">
        <header className="border-b border-border px-6 py-4">
          <div className="mb-2 flex items-center gap-3">
            <h2 className="text-base font-semibold">{data.spec_name}</h2>
            <EvalStatusBadge status={data.status} />
            <div className="ml-auto flex items-center gap-2">
              {data.status === 'done' && data.accuracy !== null && !!data.total_questions && (
                <Button variant="outline" size="sm" onClick={() => setPublishing(true)}>
                  <Upload className="h-3.5 w-3.5" /> Publish to Leaderboard
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => setConfirmingDelete(true)}
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          </div>
          <div className="mb-3 rounded border border-border bg-muted/30">
            <Url4Field value={data.url4_expression} serverUrl={serverUrl} readOnly />
          </div>
          {onRunLocally && (
            <div className="mb-3 flex items-center gap-2">
              <Button size="lg" className="flex-1" onClick={() => triggerRun(data.url4_expression)}>
                <Play className="h-4 w-4" /> Run Locally
              </Button>
              <Button variant="outline" size="lg" onClick={() => setEditing(true)}>
                <Pencil className="h-4 w-4" /> Edit
              </Button>
            </div>
          )}
          <dl className="grid grid-cols-4 gap-3 text-xs">
            <div>
              <dt className="text-muted-foreground">Accuracy</dt>
              <dd className="font-medium tabular-nums">
                {isUngradedDone(data) ? 'Not graded' : formatAccuracy(data)}
              </dd>
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
          {isUngradedDone(data) && (
            <div className="mt-3 rounded border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              Not graded — this run recorded 0 checked questions. The spec has no grading step (a{' '}
              <code>/python(check_correct.py)</code> node comparing answers to ground truth), so
              there's no accuracy to report.
            </div>
          )}
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
      {confirmingDelete && (
        <ConfirmDialog
          title="Delete this run?"
          message={`"${data.spec_name}" and its question results will be permanently removed. This can't be undone.`}
          confirmLabel={deleting ? 'Deleting…' : 'Delete'}
          destructive
          busy={deleting}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
      {editing && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title="Edit URL4 expression"
            language="url4"
            value={data.url4_expression}
            inset="10%"
            onEditorMount={mountUrl4Editor}
            confirmLabel="Save"
            confirmIcon={<Save className="h-4 w-4" />}
            onSave={(expr) => void handleSaveExpression(expr)}
            secondaryLabel="Re-run"
            secondaryIcon={<Play className="h-4 w-4" />}
            onSecondary={triggerRun}
            onClose={() => setEditing(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
