import { ipcMain, BrowserWindow } from 'electron';
import { venvManager } from '../services/venv-manager';
import { log } from '../debug-log';
import { requireTrustedIpcSender } from './sender-validation';

export function registerVenvHandlers(): void {
  ipcMain.handle('venv:detect', async (event) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:detect received`);
    const result = await venvManager.detect();
    log(`[ipc] venv:detect returning ${JSON.stringify(result)}`);
    return result;
  });

  ipcMain.handle('venv:create', async (event) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:create received`);
    const result = await venvManager.create();
    log(`[ipc] venv:create returning ${result}`);
    return result;
  });

  ipcMain.handle('venv:sync', async (event, extra?: string) => {
    requireTrustedIpcSender(event);
    log(`[ipc] venv:sync received, extra=${extra}`);
    const result = await venvManager.sync(extra);
    log(`[ipc] venv:sync returning ${result}`);
    return result;
  });

  ipcMain.handle('venv:listPackages', (event) => {
    requireTrustedIpcSender(event);
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
