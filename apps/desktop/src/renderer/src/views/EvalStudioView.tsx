import { useCallback, useEffect, useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import {
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  ScrollText,
} from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { EvalRunsList } from '@/components/eval/EvalRunsList';
import { LeaderboardLink } from '@/components/eval/LeaderboardLink';
import { EvalRunDetail } from '@/components/eval/EvalRunDetail';
import { AddEvalRunDialog } from '@/components/eval/AddEvalRunDialog';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ServerLogs } from '@/components/server/ServerLogs';
import { useStartEvalRun } from '@/hooks/use-start-eval-run';
import { useBackendStatus, isBackendStatusV2 } from '@/hooks/use-backend-status';
import { usePublishLogs } from '@/hooks/use-publish-logs';
import { referencedBackends } from '@/lib/referenced-backends';
import type { RunPayload } from '@/components/run/types';

interface EvalStudioViewProps {
  /** When set (e.g. via a deep link), starts that run and selects it on mount. */
  pendingRun?: RunPayload | null;
  /** Called after a pendingRun has been started, so the parent can clear it. */
  onPendingConsumed?: () => void;
}

export function EvalStudioView({ pendingRun, onPendingConsumed }: EvalStudioViewProps = {}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const startEvalRun = useStartEvalRun();
  const { refresh: refreshBackends } = useBackendStatus();
  const [preflight, setPreflight] = useState<{ payload: RunPayload; unavailable: string[] } | null>(
    null,
  );

  // Start a run and immediately select it so the right panel shows it running
  // (the detail panel polls running runs for live progress).
  const startRun = useCallback(
    (payload: RunPayload): void => {
      const runId = startEvalRun(payload);
      if (runId) setSelectedRunId(runId);
    },
    [startEvalRun],
  );

  // Preflight: if the spec references a model backend that isn't healthy, warn
  // the user first (the run would otherwise silently produce no scored records).
  // Advisory only — the user can start anyway, and a probe failure never blocks.
  const runAndSelect = useCallback(
    async (payload: RunPayload): Promise<void> => {
      const needed = referencedBackends(payload.expression);
      if (needed.length > 0) {
        try {
          const status = await refreshBackends();
          const unavailable = isBackendStatusV2(status)
            ? needed.filter((n) => {
                const b = status.backends?.[n];
                return !b || !b.authenticated || b.action !== 'healthy';
              })
            : [];
          if (unavailable.length > 0) {
            setPreflight({ payload, unavailable });
            return; // wait for the user's confirm
          }
        } catch {
          // status unreachable — fall through and start (don't block on a probe failure)
        }
      }
      startRun(payload);
    },
    [refreshBackends, startRun],
  );

  // Clear the right panel when the selected run is deleted.
  const handleRunDeleted = useCallback((id: string): void => {
    setSelectedRunId((current) => (current === id ? null : current));
  }, []);

  // Clear the right panel if a bulk delete removed the selected run.
  const handleBulkDeleted = useCallback((deletedIds: string[]): void => {
    setSelectedRunId((current) => (current && deletedIds.includes(current) ? null : current));
  }, []);

  // Consume a deep-linked pending run exactly once.
  const handledPendingRef = useRef<RunPayload | null>(null);
  useEffect(() => {
    if (pendingRun && handledPendingRef.current !== pendingRun) {
      handledPendingRef.current = pendingRun;
      void runAndSelect(pendingRun);
      onPendingConsumed?.();
    }
  }, [pendingRun, runAndSelect, onPendingConsumed]);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [adding, setAdding] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const { logs: publishLogs, clearLogs: clearPublishLogs } = usePublishLogs();

  const toggleLeft = () => {
    const panel = leftPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };

  const toggleRight = () => {
    const panel = rightPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div>
          <h1 className="text-[1.6875rem] font-semibold text-foreground">Eval Studio</h1>
          <p className="text-xs text-muted-foreground">
            History of evaluation runs across leaderboard entries
          </p>
        </div>
        {/* Centered between the title and the New Run button */}
        <div className="flex flex-1 justify-center">
          <LeaderboardLink />
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="mr-1" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" /> New run
          </Button>
          <Button
            variant={showLogs ? 'secondary' : 'ghost'}
            size="icon-sm"
            aria-label={showLogs ? 'Hide publish logs' : 'Show publish logs'}
            aria-pressed={showLogs}
            title="Publish logs"
            onClick={() => setShowLogs((v) => !v)}
          >
            <ScrollText />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={leftCollapsed ? 'Show runs list' : 'Hide runs list'}
            aria-pressed={leftCollapsed}
            onClick={toggleLeft}
          >
            {leftCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={rightCollapsed ? 'Show run details' : 'Hide run details'}
            aria-pressed={rightCollapsed}
            onClick={toggleRight}
          >
            {rightCollapsed ? <PanelRightOpen /> : <PanelRightClose />}
          </Button>
        </div>
      </div>

      <ResizablePanelGroup
        direction="horizontal"
        autoSaveId="eval-studio-split"
        className="min-h-0 flex-1"
      >
        <ResizablePanel
          ref={leftPanelRef}
          id="eval-runs-list"
          order={1}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setLeftCollapsed(true)}
          onExpand={() => setLeftCollapsed(false)}
          className="overflow-hidden"
        >
          {/* Panel forces inline overflow:hidden, so scroll must live on an inner h-full container. */}
          <div className="h-full overflow-y-auto">
            <EvalRunsList
              selectedId={selectedRunId}
              onSelect={setSelectedRunId}
              onRunLocally={runAndSelect}
              onBulkDeleted={handleBulkDeleted}
            />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          ref={rightPanelRef}
          id="eval-run-detail"
          order={2}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setRightCollapsed(true)}
          onExpand={() => setRightCollapsed(false)}
          className="flex overflow-hidden"
        >
          {selectedRunId ? (
            <EvalRunDetail
              runId={selectedRunId}
              onRunLocally={runAndSelect}
              onDeleted={() => handleRunDeleted(selectedRunId)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a run to see details
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {showLogs && (
        <div className="shrink-0 px-3 pb-3">
          <ServerLogs logs={publishLogs} onClear={clearPublishLogs} title="Publish logs" />
        </div>
      )}

      {adding && <AddEvalRunDialog onClose={() => setAdding(false)} onCreate={runAndSelect} />}

      {preflight && (
        <ConfirmDialog
          title="Backend unavailable"
          message={`${preflight.unavailable.join(', ')} ${
            preflight.unavailable.length === 1 ? 'is' : 'are'
          } unavailable. This run will likely produce no scored records. Start anyway?`}
          confirmLabel="Start anyway"
          cancelLabel="Cancel"
          onConfirm={() => {
            const p = preflight.payload;
            setPreflight(null);
            startRun(p);
          }}
          onCancel={() => setPreflight(null)}
        />
      )}
    </div>
  );
}
