import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import type { BackendStatusMap, BackendHealth, BackendAlert } from '../../../../preload/types';
import { useToast } from '@/hooks/use-toast';

const actionConfig: Record<string, { dot: string; label: string }> = {
  healthy: { dot: 'bg-chart-3', label: 'Ready' },
  reauth: { dot: 'bg-chart-1', label: 'Needs Auth' },
  rate_limited: { dot: 'bg-destructive', label: 'Rate Limited' },
  degraded: { dot: 'bg-chart-1', label: 'Degraded' },
};

const backendLabels: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  gemini: 'Gemini',
};

function BackendRow({ name, health }: { name: string; health: BackendHealth }) {
  const config = actionConfig[health.action] || actionConfig.degraded;
  const label = backendLabels[name] || name;

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3 min-w-0">
        <span className={cn('h-2.5 w-2.5 rounded-full shrink-0', config.dot)} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{label}</span>
            {health.model && (
              <code className="text-xs text-muted-foreground truncate">{health.model}</code>
            )}
          </div>
          {health.action === 'healthy' && health.tokens_remaining != null && (
            <p className="text-xs text-muted-foreground">
              {Math.round(health.tokens_remaining / 1000)}k tokens remaining
            </p>
          )}
          {health.action !== 'healthy' && health.help_text && (
            <p className="text-xs text-muted-foreground truncate">{health.help_text}</p>
          )}
          {health.action !== 'healthy' && !health.help_text && health.error && (
            <p className="text-xs text-destructive truncate">{health.error}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-2">
        <span className="text-xs text-muted-foreground">{config.label}</span>
        {health.action === 'reauth' && health.cli_command && (
          <button
            onClick={() => window.electronAPI.backends.authenticate(name)}
            className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors"
          >
            Re-authenticate
          </button>
        )}
      </div>
    </div>
  );
}

export function BackendStatusPanel() {
  const [statuses, setStatuses] = useState<BackendStatusMap>({});
  const { toast } = useToast();

  useEffect(() => {
    // Load initial status
    window.electronAPI.backends.getStatus().then(setStatuses);

    // Subscribe to updates
    const unsubStatus = window.electronAPI.backends.onStatusChanged(setStatuses);

    const unsubAlert = window.electronAPI.backends.onAlert((alert: BackendAlert) => {
      const label = backendLabels[alert.backend] || alert.backend;
      if (alert.type === 'reauth') {
        toast({
          variant: 'error',
          title: `${label} needs re-authentication`,
          description: alert.health.cli_command
            ? `Run: ${alert.health.cli_command}`
            : 'Check backend credentials',
        });
      } else if (alert.type === 'rate_limited') {
        toast({
          variant: 'warning',
          title: `${label} rate limited`,
          description: 'API rate budget exhausted. Will recover automatically.',
        });
      } else if (alert.type === 'recovered') {
        toast({
          variant: 'success',
          title: `${label} recovered`,
          description: 'Backend is healthy again.',
        });
      }
    });

    return () => {
      unsubStatus();
      unsubAlert();
    };
  }, [toast]);

  const backends = Object.entries(statuses);
  if (backends.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-foreground">Backends</h3>
        <button
          onClick={() => window.electronAPI.backends.refresh()}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Refresh
        </button>
      </div>
      <div className="divide-y divide-border">
        {backends.map(([name, health]) => (
          <BackendRow key={name} name={name} health={health} />
        ))}
      </div>
    </div>
  );
}
