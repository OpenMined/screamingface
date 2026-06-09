import { useCallback, useEffect, useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Plus } from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { EvalRunsList } from '@/components/eval/EvalRunsList';
import { EvalRunDetail } from '@/components/eval/EvalRunDetail';
import { AddEvalRunDialog } from '@/components/eval/AddEvalRunDialog';
import { useStartEvalRun } from '@/hooks/use-start-eval-run';
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

  // Start a run and immediately select it so the right panel shows it running
  // (the detail panel polls running runs for live progress).
  const runAndSelect = useCallback(
    (payload: RunPayload): void => {
      const runId = startEvalRun(payload);
      if (runId) setSelectedRunId(runId);
    },
    [startEvalRun],
  );

  // Consume a deep-linked pending run exactly once.
  const handledPendingRef = useRef<RunPayload | null>(null);
  useEffect(() => {
    if (pendingRun && handledPendingRef.current !== pendingRun) {
      handledPendingRef.current = pendingRun;
      runAndSelect(pendingRun);
      onPendingConsumed?.();
    }
  }, [pendingRun, runAndSelect, onPendingConsumed]);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [adding, setAdding] = useState(false);

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
      <div className="flex items-start justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Eval Studio</h1>
          <p className="text-xs text-muted-foreground">
            History of evaluation runs across leaderboard entries
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="mr-1" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" /> New run
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
          className="overflow-auto"
        >
          <EvalRunsList
            selectedId={selectedRunId}
            onSelect={setSelectedRunId}
            onRunLocally={runAndSelect}
          />
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
            <EvalRunDetail runId={selectedRunId} onRunLocally={runAndSelect} />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a run to see details
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {adding && <AddEvalRunDialog onClose={() => setAdding(false)} onCreate={runAndSelect} />}
    </div>
  );
}
