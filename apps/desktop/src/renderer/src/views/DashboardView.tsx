import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { ServerStatusCard } from '@/components/server/ServerStatusCard';
import { ServerControls } from '@/components/server/ServerControls';
import { ServerLogs } from '@/components/server/ServerLogs';
import { BackendStatusPanel } from '@/components/server/BackendStatusPanel';
import { VenvStatusCard } from '@/components/venv/VenvStatusCard';
import { VenvSetup } from '@/components/venv/VenvSetup';
import { useServerStatus } from '@/hooks/use-server-status';
import { useVenvStatus } from '@/hooks/use-venv-status';

export function DashboardView() {
  const server = useServerStatus();
  const venv = useVenvStatus();
  const [tracingEnabled, setTracingEnabled] = useState(false);

  // Auto-start server once venv is ready
  useEffect(() => {
    if (venv.status === 'ready' && server.status === 'stopped') {
      server.start();
    }
  }, [venv.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Check if tracing plugin is enabled in config
  useEffect(() => {
    window.electronAPI.config.read().then((config) => {
      const plugins = (config.plugins as string[]) || [];
      setTracingEnabled(plugins.includes('tracing'));
    });
    const unsub = window.electronAPI.config.onChanged((config) => {
      const plugins = (config.plugins as string[]) || [];
      setTracingEnabled(plugins.includes('tracing'));
    });
    return unsub;
  }, []);

  const openPhoenix = () => {
    window.electronAPI.popup.open('http://localhost:6006', 'Phoenix Tracing');
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="font-heading text-lg font-semibold text-foreground">Dashboard</h1>

      {/* Venv status */}
      <VenvStatusCard status={venv.status} uvFound={venv.uvFound} />
      {venv.status !== 'ready' && (
        <VenvSetup
          status={venv.status}
          uvFound={venv.uvFound}
          progress={venv.progress}
          onCreate={async () => {
            const ok = await venv.create();
            if (ok) await venv.sync();
          }}
          onSync={() => venv.sync()}
        />
      )}

      {/* Server status — only show when venv is ready */}
      {venv.status === 'ready' && (
        <>
          <ServerStatusCard
            status={server.status}
            port={server.info?.port}
            scheme={server.info?.scheme}
          />
          <div className="flex items-center justify-between">
            <ServerControls
              status={server.status}
              onStart={server.start}
              onStop={server.stop}
              onRestart={server.restart}
            />
            {server.status === 'ready' && tracingEnabled && (
              <button
                onClick={openPhoenix}
                className="flex items-center gap-1.5 rounded-md bg-chart-4/15 px-3 py-1.5 text-xs font-medium text-chart-4 transition-colors hover:bg-chart-4/25"
              >
                <Activity className="h-3.5 w-3.5" />
                Phoenix Traces
              </button>
            )}
          </div>
          <BackendStatusPanel />
          <ServerLogs logs={server.logs} onClear={server.clearLogs} />
        </>
      )}
    </div>
  );
}
