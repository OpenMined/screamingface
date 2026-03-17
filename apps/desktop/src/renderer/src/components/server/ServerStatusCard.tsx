import { cn } from '@/lib/utils';
import type { ServerStatus } from '../../../../preload/types';

interface ServerStatusCardProps {
  status: ServerStatus;
  port?: number;
  scheme?: string;
}

const statusConfig: Record<ServerStatus, { color: string; label: string }> = {
  stopped: { color: 'bg-muted-foreground', label: 'Stopped' },
  starting: { color: 'bg-chart-1 animate-pulse', label: 'Starting' },
  ready: { color: 'bg-chart-3', label: 'Running' },
  error: { color: 'bg-destructive', label: 'Error' },
  restarting: { color: 'bg-chart-1 animate-pulse', label: 'Restarting' },
};

export function ServerStatusCard({ status, port, scheme }: ServerStatusCardProps) {
  const { color, label } = statusConfig[status];

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={cn('h-3 w-3 rounded-full', color)} />
          <div>
            <h3 className="text-sm font-medium text-foreground">Server</h3>
            <p className="text-xs text-muted-foreground">{label}</p>
          </div>
        </div>
        {status === 'ready' && port && (
          <code className="rounded bg-secondary px-2 py-0.5 text-xs text-chart-3">
            {scheme}://localhost:{port}
          </code>
        )}
      </div>
    </div>
  );
}
