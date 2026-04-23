import { ipcMain, BrowserWindow } from 'electron';
import { backendStatusService } from '../services/backend-status';

export function registerBackendStatusHandlers(): void {
  ipcMain.handle('backends:getStatus', () => {
    return backendStatusService.getStatus();
  });

  ipcMain.handle('backends:refresh', () => {
    return backendStatusService.refresh();
  });

  ipcMain.handle('backends:authenticate', (_event, backend: string) => {
    backendStatusService.authenticate(backend);
  });

  // Forward status changes to all renderer windows
  backendStatusService.on('statusChanged', (status) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('backends:statusChanged', status);
    }
  });

  // Forward alerts (state transitions) to all renderer windows
  backendStatusService.on('alert', (alert) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('backends:alert', alert);
    }
  });
}
