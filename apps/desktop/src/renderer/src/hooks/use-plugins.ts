import { useState, useEffect, useCallback } from 'react';
import type { PluginManifest } from '../../../preload/types';

export function usePlugins() {
  const [plugins, setPlugins] = useState<PluginManifest[]>([]);

  useEffect(() => {
    window.electronAPI.plugins.list().then(setPlugins);

    const unsub = window.electronAPI.plugins.onChanged((p) => setPlugins(p));
    return () => unsub();
  }, []);

  const install = useCallback(async (url: string) => {
    const manifest = await window.electronAPI.plugins.install(url);
    return manifest;
  }, []);

  const uninstall = useCallback((id: string) => window.electronAPI.plugins.uninstall(id), []);
  const activate = useCallback((id: string) => window.electronAPI.plugins.activate(id), []);
  const deactivate = useCallback((id: string) => window.electronAPI.plugins.deactivate(id), []);

  const activePlugins = plugins.filter((p) => p.active);

  return { plugins, activePlugins, install, uninstall, activate, deactivate };
}
