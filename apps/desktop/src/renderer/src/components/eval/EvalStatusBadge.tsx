import { cn } from '@/lib/utils';
import type { EvalRunStatus } from './types';

const STATUS_STYLES: Record<EvalRunStatus, string> = {
  running: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  done: 'bg-green-500/15 text-green-300 border-green-500/30',
  failed: 'bg-red-500/15 text-red-300 border-red-500/30',
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
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize',
        STATUS_STYLES[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
