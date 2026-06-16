import { useEffect, useRef } from 'react';
import type { VenvStatus } from '../../../../preload/types';

interface VenvSetupProps {
  status: VenvStatus;
  uvFound: boolean;
  progress: string[];
  onCreate: () => void;
  onSync: () => void;
}

export function VenvSetup({ status, uvFound, progress, onCreate, onSync }: VenvSetupProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [progress.length]);

  if (!uvFound) {
    return (
      <div className="rounded-none border border-border bg-card p-6">
        <h2 className="font-heading text-base font-semibold text-foreground">Setup Required</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">uv</code> is required but was
          not found on your system.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">Install it:</p>
        <code className="mt-2 block rounded bg-background px-3 py-2 font-mono text-xs text-chart-1">
          curl -LsSf https://astral.sh/uv/install.sh | sh
        </code>
        <p className="mt-3 text-xs text-muted-foreground">Then restart ScreamingFace.</p>
      </div>
    );
  }

  if (status === 'missing') {
    return (
      <div className="rounded-none border border-border bg-card p-6">
        <h2 className="font-heading text-base font-semibold text-foreground">
          Create Python Environment
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          No virtual environment found. Create one and install dependencies to get started.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            onClick={onCreate}
            className="rounded-none bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Create .venv
          </button>
        </div>
      </div>
    );
  }

  if (status === 'creating') {
    return (
      <div className="rounded-none border border-border bg-card p-6">
        <h2 className="font-heading text-base font-semibold text-foreground">Setting up...</h2>
        <div className="mt-3 h-32 overflow-y-auto rounded bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {progress.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    );
  }

  if (status === 'ready') {
    return (
      <div className="flex gap-2">
        <button
          onClick={onSync}
          className="rounded-none bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/80"
        >
          Sync Dependencies
        </button>
      </div>
    );
  }

  return null;
}
