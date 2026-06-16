import { cn } from '@/lib/utils';
import type { EvalRunStatus } from './types';

const STATUS_STYLES: Record<EvalRunStatus, string> = {
  running: 'bg-primary/15 text-primary border-primary/30',
  done: 'bg-gain/15 text-gain border-gain/30',
  failed: 'bg-destructive/15 text-destructive border-destructive/30',
  degraded: 'bg-primary/15 text-primary border-primary/30',
};

export function EvalStatusBadge({
  status,
  className,
}: {
  status: EvalRunStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-none border px-2 py-0.5 text-xs font-medium capitalize',
        STATUS_STYLES[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
