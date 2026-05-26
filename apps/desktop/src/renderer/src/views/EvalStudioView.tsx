import { useState } from 'react';
import { EvalRunsList } from '@/components/eval/EvalRunsList';
import { EvalRunDetail } from '@/components/eval/EvalRunDetail';

export function EvalStudioView() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Eval Studio</h1>
        <p className="text-xs text-muted-foreground">
          History of evaluation runs across leaderboard entries
        </p>
      </div>
      <div className="flex min-h-0 flex-1">
        <aside className="w-1/2 overflow-auto border-r border-border">
          <EvalRunsList selectedId={selectedRunId} onSelect={setSelectedRunId} />
        </aside>
        <main className="flex min-h-0 flex-1 overflow-hidden">
          {selectedRunId ? (
            <EvalRunDetail runId={selectedRunId} />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a run to see details
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
