import { ipcMain } from 'electron';
import { venvManager } from '../services/venv-manager';
import { log } from '../debug-log';
import { broadcastToRenderers } from './broadcast';

export function registerVenvHandlers(): void {
  ipcMain.handle('venv:detect', async () => {
    log(`[ipc] venv:detect received`);
    const result = await venvManager.detect();
    log(`[ipc] venv:detect returning ${JSON.stringify(result)}`);
    return result;
  });

  ipcMain.handle('venv:create', async () => {
    log(`[ipc] venv:create received`);
    const result = await venvManager.create();
    log(`[ipc] venv:create returning ${result}`);
    return result;
  });

  ipcMain.handle('venv:sync', async (_event, extra?: string) => {
    log(`[ipc] venv:sync received, extra=${extra}`);
    const result = await venvManager.sync(extra);
    log(`[ipc] venv:sync returning ${result}`);
    return result;
  });

  ipcMain.handle('venv:listPackages', () => {
    return venvManager.listPackages();
  });

  venvManager.on('status', (status) => {
    broadcastToRenderers('venv:statusChanged', status);
  });

  venvManager.on('progress', (line) => {
    broadcastToRenderers('venv:progress', line);
  });
}
