// apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx
import { useEffect, useMemo, useState } from 'react';
import { X, Upload, ExternalLink, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Url4Field } from '@/components/Url4Field';
import { useToast } from '@/hooks/use-toast';
import { usePublishScore } from '@/hooks/use-publish-score';
import {
  parseSpecName,
  deriveProviders,
  hasLocalDataRefs,
  sanitizeDataRefs,
} from '@/lib/url4-redaction';
import { publishBlockReason } from '@/lib/publish-guard';
import {
  deriveBenchmarkIdentity,
  verifyIdentityConsistency,
  type BenchmarkIdentity,
} from '@/lib/benchmark-identity';
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

// Submitter name is remembered across publishes within a session so it doesn't
// have to be re-typed each time. Matches the sessionStorage usage elsewhere in
// the renderer (see federation/registry.ts for the localStorage analogue).
const SUBMITTER_KEY = 'sf-leaderboard-submitter';

function loadSubmitter(): string {
  try {
    return window.sessionStorage.getItem(SUBMITTER_KEY) ?? '';
  } catch {
    return '';
  }
}

function saveSubmitter(name: string): void {
  try {
    window.sessionStorage.setItem(SUBMITTER_KEY, name);
  } catch {
    // sessionStorage unavailable — non-fatal, just skip persistence.
  }
}

export function PublishToLeaderboardDialog({ run, serverUrl, onClose }: Props) {
  const { toast } = useToast();
  const { publish, status, error, result } = usePublishScore();

  const parsed = useMemo(() => parseSpecName(run.spec_name), [run.spec_name]);
  const hasDataRefs = useMemo(() => hasLocalDataRefs(run.url4_expression), [run.url4_expression]);

  // SF-300: the benchmark identity (id + label + dataset filename + content
  // signature) is AUTO-DERIVED from the run — never typed. We derive it async
  // because the signature is a Web Crypto SHA-256 digest over the run's content.
  const [identity, setIdentity] = useState<BenchmarkIdentity | null>(null);
  useEffect(() => {
    let cancelled = false;
    void deriveBenchmarkIdentity(run).then((next) => {
      if (!cancelled) setIdentity(next);
    });
    return () => {
      cancelled = true;
    };
  }, [run]);

  const [specId, setSpecId] = useState(parsed.spec_id);
  const [providersText, setProvidersText] = useState(
    deriveProviders(run.url4_expression).join(', '),
  );
  const [submittedBy, setSubmittedBy] = useState(loadSubmitter);
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
  // Preflight: deterministic scoreboard-contract violations we can catch before
  // the round-trip (e.g. a zero-question degraded run) — block + explain up front.
  const blockReason = useMemo(
    () => publishBlockReason({ run, url4Expression: expressionToPublish }),
    [run, expressionToPublish],
  );
  // Verify the derived benchmark id <-> content signature are internally
  // consistent (id derivable + content available to sign) before allowing a
  // publish. Disagreement (e.g. a run with no graded content) blocks here.
  const identityCheck = useMemo(
    () => (identity ? verifyIdentityConsistency(identity) : { ok: false, reason: null }),
    [identity],
  );
  // Block publish until: run is publishable, identity derived + consistent, and
  // any /data refs are either sanitized or explicitly acknowledged.
  const redactionResolved = !hasDataRefs || sanitize || ackExpose;
  const canPublish =
    !blockReason && !!identity && identityCheck.ok && specId.trim().length > 0 && redactionResolved;

  const handlePublish = async (): Promise<void> => {
    if (!identity) return;
    // Remember the entered name for subsequent publishes this session, whether
    // or not the round-trip ultimately succeeds.
    saveSubmitter(submittedBy.trim());
    const out = await publish({
      run,
      benchmarkId: identity.id,
      benchmarkSignature: identity.signature,
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
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-none border border-border bg-card">
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
              <CheckCircle2 className="mx-auto h-10 w-10 text-gain" />
              <p className="text-sm font-medium text-foreground">Published to the leaderboard.</p>
              <Button variant="outline" onClick={handleViewLeaderboard}>
                <ExternalLink className="h-4 w-4" /> View on leaderboard
              </Button>
            </div>
          ) : (
            <>
              {/* Preflight block — this run can't satisfy the scoreboard contract */}
              {blockReason && (
                <div className="flex items-start gap-1.5 rounded-none border border-primary/40 bg-primary/10 px-3 py-2 text-xs text-foreground">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                  <span>{blockReason}</span>
                </div>
              )}

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
                  <Url4Field value={expressionToPublish} serverUrl={serverUrl} readOnly />
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

              {/* benchmark identity (auto-derived, read-only) + spec id */}
              <div className="grid grid-cols-2 gap-3">
                <div className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Benchmark
                  </span>
                  {/* Derived from the dataset filename in the URL4 expression and
                      pinned by a content signature — not editable (SF-300). */}
                  <div
                    data-testid="benchmark-identity"
                    className="w-full rounded-none border border-border bg-muted/30 px-3 py-2 text-sm text-foreground"
                    title={identity?.datasetFilename ?? undefined}
                  >
                    {identity ? (
                      <>
                        <span className="font-medium">{identity.label || identity.id || '—'}</span>
                        {identity.id && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            ({identity.id})
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-muted-foreground">Deriving…</span>
                    )}
                  </div>
                  {identity && (
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                      {identity.datasetFilename
                        ? `From ${identity.datasetFilename}`
                        : 'Derived from the run’s spec (no dataset file in the expression).'}
                      {identity.signature && (
                        <>
                          {' '}
                          · signature{' '}
                          <code className="font-mono">{identity.signature.slice(0, 12)}…</code>
                        </>
                      )}
                    </p>
                  )}
                </div>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-muted-foreground">
                    Spec ID <span className="text-destructive">*</span>
                  </span>
                  <input
                    className="w-full rounded-none border border-border bg-background px-3 py-2 text-sm"
                    value={specId}
                    onChange={(e) => setSpecId(e.target.value)}
                  />
                </label>
              </div>

              {/* Identity consistency: id<->signature must agree before publish. */}
              {identity && !identityCheck.ok && identityCheck.reason && (
                <div className="flex items-start gap-1.5 rounded-none border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{identityCheck.reason}</span>
                </div>
              )}

              {/* providers (editable) */}
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-muted-foreground">
                  Providers (comma-separated)
                </span>
                <input
                  className="w-full rounded-none border border-border bg-background px-3 py-2 text-sm"
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
                  className="w-full rounded-none border border-border bg-background px-3 py-2 text-sm"
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
