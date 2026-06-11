import { Play, Square, RotateCw } from 'lucide-react';
import type { ServerStatus } from '../../../../preload/types';

interface ServerControlsProps {
  status: ServerStatus;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
}

export function ServerControls({ status, onStart, onStop, onRestart }: ServerControlsProps) {
  const running = status === 'ready';
  const busy = status === 'starting' || status === 'restarting';

  return (
    <div className="flex gap-2">
      {!running && !busy && (
        <button
          onClick={onStart}
          className="flex items-center gap-1.5 rounded-md bg-gain/15 px-3 py-1.5 text-xs font-medium text-gain transition-colors hover:bg-gain/25"
        >
          <Play className="h-3.5 w-3.5" />
          Start
        </button>
      )}
      {running && (
        <>
          <button
            onClick={onStop}
            className="flex items-center gap-1.5 rounded-md bg-destructive/15 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/25"
          >
            <Square className="h-3.5 w-3.5" />
            Stop
          </button>
          <button
            onClick={onRestart}
            className="flex items-center gap-1.5 rounded-md bg-chart-1/15 px-3 py-1.5 text-xs font-medium text-chart-1 transition-colors hover:bg-chart-1/25"
          >
            <RotateCw className="h-3.5 w-3.5" />
            Restart
          </button>
        </>
      )}
      {busy && (
        <span className="px-3 py-1.5 text-xs text-muted-foreground">
          {status === 'starting' ? 'Starting...' : 'Restarting...'}
        </span>
      )}
    </div>
  );
}
