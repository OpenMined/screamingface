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
    async (_event, backend: string, profileName?: string): Promise<LauncherResult> => {
      const sfBaseUrl = backendStatusService.getServerUrl();
      console.log(
        `[oauth] authenticateOAuth invoked: backend=${backend} profileName=${profileName ?? '(default)'} sfBaseUrl=${sfBaseUrl ?? 'NULL'}`,
      );
      if (!sfBaseUrl) {
        return {
          kind: 'failed',
          reason: 'gateway_error',
          message: 'SF server is not running',
        };
      }
      const result = await runOAuthLauncher({ sfBaseUrl, backendName: backend, profileName });
      console.log(`[oauth] launcher result:`, result);
      return result;
    },
  );

  ipcMain.handle('backends:listProfiles', async (_event, backend: string) => {
    const sfBaseUrl = backendStatusService.getServerUrl();
    if (!sfBaseUrl) {
      return { profiles: [], error: 'gateway_unreachable' };
    }
    try {
      const resp = await fetch(`${sfBaseUrl}/${backend}/auth/profiles`);
      if (!resp.ok) {
        return { profiles: [], error: 'gateway_unreachable' };
      }
      const body = (await resp.json()) as { profiles?: unknown[] };
      return { profiles: body.profiles ?? [] };
    } catch {
      return { profiles: [], error: 'gateway_unreachable' };
    }
  });

  ipcMain.handle(
    'backends:deleteProfile',
    async (_event, backend: string, profileName: string) => {
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0 };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/profiles/${encodeURIComponent(profileName)}`,
          { method: 'DELETE' },
        );
        if (resp.status === 204) return { ok: true };
        return { ok: false, status: resp.status };
      } catch {
        return { ok: false, status: 0 };
      }
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
