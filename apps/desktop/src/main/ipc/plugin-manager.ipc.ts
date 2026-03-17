import { ipcMain, BrowserWindow } from 'electron';
import { pluginRegistry } from '../services/plugin-registry';
import { venvManager } from '../services/venv-manager';

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
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('plugins:changed', plugins);
    }
  });
}
