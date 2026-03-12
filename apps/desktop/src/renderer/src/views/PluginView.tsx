import { useState, useEffect, useCallback } from 'react';
import { PluginBrowser } from '@/components/plugins/PluginBrowser';
import { PluginCard } from '@/components/plugins/PluginCard';
import { usePlugins } from '@/hooks/use-plugins';

export function PluginView() {
  const { plugins, install, uninstall, activate, deactivate } = usePlugins();

  const handleInstall = useCallback(
    async (url: string) => {
      await install(url);
    },
    [install],
  );

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="font-heading text-lg font-semibold text-foreground">Plugins</h1>
      <p className="text-sm text-muted-foreground">
        Load remote UI plugins from CDN URLs. Each plugin renders inside the app as a sidebar
        entry.
      </p>

      <PluginBrowser onInstall={handleInstall} />

      {plugins.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Installed
          </h2>
          {plugins.map((p) => (
            <PluginCard
              key={p.id}
              plugin={p}
              onActivate={activate}
              onDeactivate={deactivate}
              onUninstall={uninstall}
            />
          ))}
        </div>
      )}
    </div>
  );
}
