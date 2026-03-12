import { ipcMain, BrowserWindow } from 'electron';
import { venvManager } from '../services/venv-manager';

export function registerVenvHandlers(): void {
  ipcMain.handle('venv:detect', () => {
    return venvManager.detect();
  });

  ipcMain.handle('venv:create', () => {
    return venvManager.create();
  });

  ipcMain.handle('venv:sync', (_event, extra?: string) => {
    return venvManager.sync(extra);
  });

  ipcMain.handle('venv:listPackages', () => {
    return venvManager.listPackages();
  });

  venvManager.on('status', (status) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('venv:statusChanged', status);
    }
  });

  venvManager.on('progress', (line) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('venv:progress', line);
    }
  });
}
