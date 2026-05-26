import { useState, useEffect, useCallback } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import type { View } from '@/components/layout/Sidebar';
import { DashboardView } from '@/views/DashboardView';
import { SessionsView } from '@/views/SessionsView';
import { EvalStudioView } from '@/views/EvalStudioView';
import { SettingsView } from '@/views/SettingsView';
import { PluginHost } from '@/components/plugins/PluginHost';
import { useServerStatus } from '@/hooks/use-server-status';
import { usePlugins } from '@/hooks/use-plugins';

export function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard');
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const server = useServerStatus();
  const { activePlugins } = usePlugins();

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

  const serverUrl = server.info
    ? `${server.info.scheme}://${server.info.host === '0.0.0.0' ? 'localhost' : server.info.host}:${server.info.port}`
    : '';

  const renderView = () => {
    if (currentView === 'dashboard') return <DashboardView server={server} />;
    if (currentView === 'sessions') return <SessionsView />;
    if (currentView === 'eval-studio') return <EvalStudioView />;
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

    return <DashboardView server={server} />;
  };

  return (
    <AppShell
      currentView={currentView}
      onNavigate={setCurrentView}
      serverStatus={server.status}
      serverPort={server.info?.port}
      plugins={activePlugins}
    >
      {renderView()}
    </AppShell>
  );
}
