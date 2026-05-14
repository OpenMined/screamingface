import { ipcMain } from 'electron';
import { pluginRegistry } from '../services/plugin-registry';
import { venvManager } from '../services/venv-manager';
import { broadcastToRenderers } from './broadcast';

export function registerPluginHandlers(): void {
  ipcMain.handle('plugins:list', () => {
    return pluginRegistry.list();
  });

  ipcMain.handle('plugins:discover', () => {
    return venvManager.discoverPlugins();
  });

  ipcMain.handle('plugins:install', (_event, url: string) => {
    return pluginRegistry.install(url);
  });

  ipcMain.handle('plugins:uninstall', (_event, id: string) => {
    return pluginRegistry.uninstall(id);
  });

  ipcMain.handle('plugins:activate', (_event, id: string) => {
    return pluginRegistry.activate(id);
  });

  ipcMain.handle('plugins:deactivate', (_event, id: string) => {
    return pluginRegistry.deactivate(id);
  });

  ipcMain.handle('plugins:getCatalog', () => {
    return pluginRegistry.getCatalog();
  });

  pluginRegistry.on('changed', () => {
    const plugins = pluginRegistry.list();
    broadcastToRenderers('plugins:changed', plugins);
  });
}
