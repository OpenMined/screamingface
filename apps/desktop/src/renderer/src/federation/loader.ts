import { loadRemoteModule } from '@softarc/native-federation-runtime';
import type { PluginComponent, PluginModule } from './types';

const cache = new Map<string, PluginComponent>();

export async function loadPlugin(
  remoteName: string,
  exposedModule: string,
): Promise<PluginComponent> {
  const key = `${remoteName}/${exposedModule}`;

  if (cache.has(key)) {
    return cache.get(key)!;
  }

  const module = (await loadRemoteModule({
    remoteName,
    exposedModule,
  })) as PluginModule;

  const component = module.default;
  cache.set(key, component);
  return component;
}

export function clearPluginCache(): void {
  cache.clear();
}
