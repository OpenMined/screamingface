import { ipcMain, BrowserWindow } from 'electron';
import { pluginRegistry } from '../services/plugin-registry';
import { venvManager } from '../services/venv-manager';
import { requireTrustedIpcSender } from './sender-validation';

export function registerPluginHandlers(): void {
  ipcMain.handle('plugins:list', (event) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.list();
  });

  ipcMain.handle('plugins:discover', (event) => {
    requireTrustedIpcSender(event);
    return venvManager.discoverPlugins();
  });

  ipcMain.handle('plugins:install', (event, url: string) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.install(url);
  });

  ipcMain.handle('plugins:uninstall', (event, id: string) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.uninstall(id);
  });

  ipcMain.handle('plugins:activate', (event, id: string) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.activate(id);
  });

  ipcMain.handle('plugins:deactivate', (event, id: string) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.deactivate(id);
  });

  ipcMain.handle('plugins:getCatalog', (event) => {
    requireTrustedIpcSender(event);
    return pluginRegistry.getCatalog();
  });

  pluginRegistry.on('changed', () => {
    const plugins = pluginRegistry.list();
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('plugins:changed', plugins);
    }
  });
}
