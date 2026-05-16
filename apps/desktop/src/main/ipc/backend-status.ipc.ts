import { ipcMain, BrowserWindow } from 'electron';
import { backendStatusService } from '../services/backend-status';
import {
  runOAuthLauncher,
  getPendingAuthState,
  clearPendingAuthState,
  type LauncherResult,
} from '../services/oauth-launcher';
import { isSafeBackendName } from '../services/external-url-policy';
import { requireTrustedIpcSender } from './sender-validation';

export type ExchangeCodeResult = { ok: true } | { ok: false; status?: number; message?: string };

export function registerBackendStatusHandlers(): void {
  ipcMain.handle('backends:getStatus', (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.getStatus();
  });

  ipcMain.handle('backends:refresh', (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.refresh();
  });

  ipcMain.handle('backends:authenticate', (event, backend: string) => {
    requireTrustedIpcSender(event);
    backendStatusService.authenticate(backend);
  });

  ipcMain.handle(
    'backends:authenticateOAuth',
    async (event, backend: string, profileName?: string): Promise<LauncherResult> => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { kind: 'failed', reason: 'gateway_error', message: 'invalid backend name' };
      }
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

  ipcMain.handle('backends:getPendingAuthState', (event, backend: string): string | null => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) return null;
    return getPendingAuthState(backend);
  });

  ipcMain.handle(
    'backends:exchangeOAuthCode',
    async (event, backend: string, code: string): Promise<ExchangeCodeResult> => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, message: `invalid backend name: ${backend}` };
      }

      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, message: 'SF server is not running' };
      }
      const state = getPendingAuthState(backend);
      if (!state) {
        return { ok: false, message: 'No in-flight OAuth flow for this backend' };
      }
      try {
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/exchange-code`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ code, state }),
        });
        if (resp.ok) {
          clearPendingAuthState(backend);
          return { ok: true };
        }
        let message: string | undefined;
        try {
          const body = (await resp.json()) as { detail?: { code?: string; message?: string } };
          message = body.detail?.message ?? body.detail?.code;
        } catch {
          /* ignore */
        }
        return { ok: false, status: resp.status, message };
      } catch (e) {
        return { ok: false, message: e instanceof Error ? e.message : String(e) };
      }
    },
  );

  ipcMain.handle('backends:listProfiles', async (event, backend: string) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { profiles: [], error: 'invalid_backend' };
    }

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

  ipcMain.handle('backends:deleteProfile', async (event, backend: string, profileName: string) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { ok: false, status: 400 };
    }

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
