import { useState, useEffect, useCallback } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import type { View } from '@/components/layout/Sidebar';
import { DashboardView } from '@/views/DashboardView';
import { SessionsView } from '@/views/SessionsView';
import { EvalStudioView } from '@/views/EvalStudioView';
import { Url4StudioView } from '@/views/Url4StudioView';
import { SettingsView } from '@/views/SettingsView';
import { PluginHost } from '@/components/plugins/PluginHost';
import { useServerStatus } from '@/hooks/use-server-status';
import { usePlugins } from '@/hooks/use-plugins';
import { useAigwSession } from '@/hooks/use-aigw-session';
import { AigwLoginDialog } from '@/components/AigwLoginDialog';
import type { RunPayload } from '@/components/run/types';

export function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard');
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [pendingRun, setPendingRun] = useState<RunPayload | null>(null);
  const [aigwLoginOpen, setAigwLoginOpen] = useState(false);
  const server = useServerStatus();
  const { activePlugins } = usePlugins();
  const aigwSession = useAigwSession();

  useEffect(() => {
    window.electronAPI.config.read().then(setConfig);
    return window.electronAPI.config.onChanged(setConfig);
  }, []);

  const handleConfigChange = useCallback(
    (patch: Partial<Record<string, unknown>>) => {
      const updated = { ...config, ...patch };
      window.electronAPI.config.write(updated);
    },
    [config],
  );

  const openRun = useCallback((payload: RunPayload) => {
    // The run experience now lives inside Eval Studio; deep links land there
    // and the view starts + selects the run.
    setPendingRun(payload);
    setCurrentView('eval-studio');
  }, []);

  useEffect(() => {
    const onPayload = (
      window.electronAPI as {
        deepLink?: { onPayload?: (cb: (p: RunPayload) => void) => () => void };
      }
    ).deepLink?.onPayload;
    return onPayload?.(openRun);
  }, [openRun]);

  useEffect(() => {
    if (aigwSession.expiredNonce > 0) setAigwLoginOpen(true);
  }, [aigwSession.expiredNonce]);

  const openAigwLogin = useCallback(() => {
    setAigwLoginOpen(true);
  }, []);

  const refreshBackends = useCallback(() => {
    void window.electronAPI.backends.refresh();
  }, []);

  const serverUrl = server.info
    ? `${server.info.scheme}://${server.info.host === '0.0.0.0' ? 'localhost' : server.info.host}:${server.info.port}`
    : '';

  const renderView = () => {
    if (currentView === 'dashboard') {
      return <DashboardView server={server} onAigwLoginRequest={openAigwLogin} />;
    }
    if (currentView === 'sessions') return <SessionsView />;
    if (currentView === 'eval-studio') {
      return (
        <EvalStudioView pendingRun={pendingRun} onPendingConsumed={() => setPendingRun(null)} />
      );
    }
    if (currentView === 'url4-studio') return <Url4StudioView />;
    if (currentView === 'settings') return <SettingsView />;

    if (currentView.startsWith('plugin:')) {
      const pluginId = currentView.slice('plugin:'.length);
      const plugin = activePlugins.find((p) => p.id === pluginId);

      if (!plugin) {
        return (
          <div className="p-6 text-sm text-muted-foreground">Plugin not found or inactive.</div>
        );
      }

      return (
        <PluginHost
          pluginId={plugin.id}
          exposedModule={plugin.exposedModule}
          serverUrl={serverUrl}
          config={config}
          onConfigChange={handleConfigChange}
        />
      );
    }

    return <DashboardView server={server} onAigwLoginRequest={openAigwLogin} />;
  };

  return (
    <AppShell
      currentView={currentView}
      onNavigate={setCurrentView}
      serverStatus={server.status}
      serverPort={server.info?.port}
      plugins={activePlugins}
      onAigwLoginRequest={openAigwLogin}
    >
      {renderView()}
      <AigwLoginDialog
        open={aigwLoginOpen}
        session={aigwSession}
        onClose={() => setAigwLoginOpen(false)}
        onSignedIn={refreshBackends}
      />
    </AppShell>
  );
}
