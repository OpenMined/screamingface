import { cn } from '@/lib/utils';
import type { VenvStatus } from '../../../../preload/types';

const statusConfig: Record<VenvStatus, { color: string; label: string }> = {
  unknown: { color: 'bg-muted-foreground', label: 'Checking...' },
  checking: { color: 'bg-chart-1 animate-pulse', label: 'Checking...' },
  missing: { color: 'bg-chart-2', label: 'Not found' },
  creating: { color: 'bg-chart-1 animate-pulse', label: 'Creating...' },
  ready: { color: 'bg-gain', label: 'Ready' },
  error: { color: 'bg-destructive', label: 'Error' },
};

interface VenvStatusCardProps {
  status: VenvStatus;
  uvFound: boolean;
}

export function VenvStatusCard({ status, uvFound }: VenvStatusCardProps) {
  const { color, label } = statusConfig[status];

  return (
    <div className="rounded-none border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <span className={cn('h-3 w-3 rounded-none', color)} />
        <div>
          <h3 className="text-sm font-medium text-foreground">Python Environment</h3>
          <p className="text-xs text-muted-foreground">
            {!uvFound ? 'uv not found — install it to continue' : label}
          </p>
        </div>
      </div>
    </div>
  );
}
