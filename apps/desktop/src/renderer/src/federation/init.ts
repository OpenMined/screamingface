import { initFederation } from '@softarc/native-federation-runtime';
import type { PluginManifest } from './types';

let initialized = false;

export async function initPluginFederation(plugins: PluginManifest[]): Promise<void> {
  if (initialized) return;

  const remotes: Record<string, string> = {};
  for (const plugin of plugins) {
    if (plugin.active) {
      remotes[plugin.id] = plugin.remoteEntryUrl;
    }
  }

  await initFederation({ name: 'screamingface-host', shared: {} }, { remotes });
  initialized = true;
}

export function resetFederation(): void {
  initialized = false;
}
