// apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx
import { useMemo, useState } from 'react';
import { X, Upload, ExternalLink, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Url4Viewer } from '@/components/Url4Viewer';
import { useToast } from '@/hooks/use-toast';
import { usePublishScore } from '@/hooks/use-publish-score';
import {
  parseSpecName,
  deriveProviders,
  hasLocalDataRefs,
  sanitizeDataRefs,
} from '@/lib/url4-redaction';
import type { EvalRunDetail } from './types';

interface Props {
  run: EvalRunDetail;
  serverUrl: string;
  onClose: () => void;
}

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

export function PublishToLeaderboardDialog({ run, serverUrl, onClose }: Props) {
  const { toast } = useToast();
  const { publish, status, error, result } = usePublishScore();

  const parsed = useMemo(() => parseSpecName(run.spec_name), [run.spec_name]);
  const hasDataRefs = useMemo(() => hasLocalDataRefs(run.url4_expression), [run.url4_expression]);

  const [benchmarkId, setBenchmarkId] = useState(parsed.benchmark_id ?? '');
  const [specId, setSpecId] = useState(parsed.spec_id);
  const [providersText, setProvidersText] = useState(
    deriveProviders(run.url4_expression).join(', '),
  );
  const [submittedBy, setSubmittedBy] = useState('');
  // Redaction choices: only relevant when the expression references /data blobs.
  const [sanitize, setSanitize] = useState(hasDataRefs);
  const [ackExpose, setAckExpose] = useState(false);

  const expressionToPublish = sanitize
    ? sanitizeDataRefs(run.url4_expression)
    : run.url4_expression;

  const providers = providersText
    .split(',')
    .map((p) => p.trim())
    .filter((p) => p.length > 0);

  const submitting = status === 'submitting';
  // Block publish until: benchmark known, and any /data refs are either sanitized
  // or explicitly acknowledged as exposing local data.
  const redactionResolved = !hasDataRefs || sanitize || ackExpose;
  const canPublish = benchmarkId.trim().length > 0 && specId.trim().length > 0 && redactionResolved;

  const handlePublish = async (): Promise<void> => {
    const out = await publish({
      run,
      benchmarkId: benchmarkId.trim(),
      specId: specId.trim(),
      url4Expression: expressionToPublish,
      providers,
      submittedBy: submittedBy.trim() || null,
    });
    if (out) {
      toast({ variant: 'success', title: 'Published to the leaderboard' });
    } else {
      // error state is rendered inline; surface a toast too for visibility.
      toast({ variant: 'error', title: 'Publish failed', description: error ?? undefined });
    }
  };

  const handleViewLeaderboard = (): void => {
    if (result) void window.electronAPI.publish.openExternal(result.portalLink);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16">
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-[10px] border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">
            Publish this run to the public leaderboard?
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-4">
          {status === 'success' && result ? (
            <div className="space-y-4 py-6 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-chart-3" />
              <p className="text-sm font-medium text-foreground">Published to the leaderboard.</p>
              <Button variant="outline" onClick={handleViewLeaderboard}>
                <ExternalLink className="h-4 w-4" /> View on leaderboard
              </Button>
            </div>
          ) : (
            <>
              {/* Aggregate (read-only) */}
              <dl className="grid grid-cols-3 gap-3 text-xs">
                <div>
                  <dt className="text-muted-foreground">Accuracy</dt>
                  <dd className="font-medium tabular-nums">{formatPercent(run.accuracy)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Correct / Total</dt>
                  <dd className="font-medium tabular-nums">
                    {run.correct_questions ?? 0} / {run.total_questions ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Providers</dt>
                  <dd className="font-medium">{providers.join(', ') || '—'}</dd>
                </div>
              </dl>

              {/* url4 expression (read-only) + redaction warning */}
              <div>
                <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  URL4 expression {sanitize && hasDataRefs ? '(sanitized)' : ''}
                </span>
                <div className="rounded bg-muted/30 px-3 py-2">
                  <Url4Viewer expression={expressionToPublish} serverUrl={serverUrl} />
                </div>
                {hasDataRefs && (
                  <div className="mt-2 rounded border border-chart-5/40 bg-chart-5/10 px-3 py-2 text-xs">
                    <p className="flex items-start gap-1.5 text-foreground">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-chart-5" />
                      This expression references local <code>/data</code> blobs that only exist on
                      your machine. The published version won&apos;t be runnable by others.
                    </p>
                    <label className="mt-2 flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={sanitize}
                        onChange={(e) => {
                          setSanitize(e.target.checked);
                          if (e.target.checked) setAckExpose(false);
                        }}
                      />
                      Sanitize — replace local data refs with <code>/data/&lt;redacted&gt;</code>
                    </label>
                    {!sanitize && (
                      <label className="mt-1 flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={ackExpose}
                          onChange={(e) => setAckExpose(e.target.checked)}
                        />
                        I understand this exposes my local data refs
                      </label>
                    )}
                  </div>
                )}
              </div>

              {/* benchmark / spec ids */}
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Benchmark ID <span className="text-destructive">*</span>
                  </span>
                  <input
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    value={benchmarkId}
                    placeholder="e.g. hle"
                    onChange={(e) => setBenchmarkId(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Spec ID <span className="text-destructive">*</span>
                  </span>
                  <input
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    value={specId}
                    onChange={(e) => setSpecId(e.target.value)}
                  />
                </label>
              </div>

              {/* providers (editable) */}
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted-foreground">
                  Providers (comma-separated)
                </span>
                <input
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  value={providersText}
                  placeholder="claude, codex, gemini"
                  onChange={(e) => setProvidersText(e.target.value)}
                />
              </label>

              {/* submitter */}
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted-foreground">
                  Submitter name
                </span>
                <input
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  value={submittedBy}
                  placeholder="leave blank for anonymous"
                  onChange={(e) => setSubmittedBy(e.target.value)}
                />
              </label>

              {/* privacy notice */}
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Your aggregate result, the URL4 expression, and the submitter name (if provided)
                will be public. Per-question details stay on your machine.
              </p>

              {error && (
                <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          {status === 'success' ? (
            <Button onClick={onClose}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={submitting}>
                Cancel
              </Button>
              <Button onClick={handlePublish} disabled={!canPublish || submitting}>
                <Upload className="h-4 w-4" />
                {submitting ? 'Publishing…' : error ? 'Retry' : 'Publish'}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
