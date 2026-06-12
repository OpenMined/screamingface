import { cn } from '@/lib/utils';
import type { ServerStatus } from '../../../../preload/types';

const statusColors: Record<ServerStatus, string> = {
  stopped: 'bg-muted-foreground',
  starting: 'bg-chart-1 animate-pulse',
  ready: 'bg-gain',
  error: 'bg-destructive',
  restarting: 'bg-chart-1 animate-pulse',
};

const statusLabels: Record<ServerStatus, string> = {
  stopped: 'Stopped',
  starting: 'Starting...',
  ready: 'Running',
  error: 'Error',
  restarting: 'Restarting...',
};

interface StatusBarProps {
  serverStatus: ServerStatus;
  serverPort?: number;
}

export function StatusBar({ serverStatus, serverPort }: StatusBarProps) {
  return (
    <div className="flex items-center justify-between border-t border-border bg-card px-4 py-1.5 text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span className={cn('h-2 w-2 rounded-none', statusColors[serverStatus])} />
        <span>Server: {statusLabels[serverStatus]}</span>
        {serverStatus === 'ready' && serverPort && (
          <span className="text-foreground/60">:{serverPort}</span>
        )}
      </div>
      <span className="font-mono">screamingface v0.1.0</span>
    </div>
  );
}
