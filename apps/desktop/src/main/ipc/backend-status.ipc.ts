import { ipcMain, BrowserWindow } from 'electron';
import { backendStatusService } from '../services/backend-status';
import { runOAuthLauncher, type LauncherResult } from '../services/oauth-launcher';

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

  ipcMain.handle(
    'backends:authenticateOAuth',
    async (_event, backend: string): Promise<LauncherResult> => {
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return {
          kind: 'failed',
          reason: 'gateway_error',
          message: 'SF server is not running',
        };
      }
      return await runOAuthLauncher({ sfBaseUrl, backendName: backend });
    },
  );

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
