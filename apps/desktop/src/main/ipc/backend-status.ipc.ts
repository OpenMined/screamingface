import { ipcMain, BrowserWindow } from 'electron';
import { backendStatusService, isStatusV2 } from '../services/backend-status';
import {
  runOAuthLauncher,
  runOAuthConnectionLauncher,
  getPendingAuthState,
  getPendingConnectionAuthState,
  clearPendingAuthState,
  clearPendingConnectionAuthState,
  type LauncherResult,
} from '../services/oauth-launcher';
import { isSafeBackendName, isSafeOAuthConnectionId } from '../services/external-url-policy';
import { desktopSecretHeader } from '../services/desktop-secret';
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

  ipcMain.handle('backends:loginGateway', async (event, username: string, password: string) => {
    requireTrustedIpcSender(event);
    return backendStatusService.loginGateway(username, password);
  });

  ipcMain.handle('backends:logoutGateway', async (event) => {
    requireTrustedIpcSender(event);
    return backendStatusService.logoutGateway();
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
      const result = await runOAuthLauncher({
        sfBaseUrl,
        backendName: backend,
        profileName,
        headers: desktopSecretHeader(),
        allowedOAuthRedirectPorts: currentGatewayRedirectPorts(),
      });
      console.log(`[oauth] launcher result:`, result);
      return result;
    },
  );

  ipcMain.handle(
    'backends:authenticateOAuthConnection',
    async (event, backend: string, label?: string): Promise<LauncherResult> => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { kind: 'failed', reason: 'gateway_error', message: 'invalid backend name' };
      }
      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return {
          kind: 'failed',
          reason: 'gateway_error',
          message: 'SF server is not running',
        };
      }
      return await runOAuthConnectionLauncher({
        sfBaseUrl,
        backendName: backend,
        label,
        headers: desktopSecretHeader(),
        allowedOAuthRedirectPorts: currentGatewayRedirectPorts(),
      });
    },
  );

  ipcMain.handle(
    'backends:getPendingAuthState',
    (event, backend: string, profileName?: string): string | null => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) return null;
      return getPendingAuthState(backend, profileName);
    },
  );

  ipcMain.handle(
    'backends:getPendingConnectionAuthState',
    (event, backend: string, connectionId?: string): string | null => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend) || !connectionId || !isSafeOAuthConnectionId(connectionId)) {
        return null;
      }
      return getPendingConnectionAuthState(backend, connectionId);
    },
  );

  ipcMain.handle(
    'backends:exchangeOAuthCode',
    async (
      event,
      backend: string,
      code: string,
      profileName?: string,
    ): Promise<ExchangeCodeResult> => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, message: `invalid backend name: ${backend}` };
      }

      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, message: 'SF server is not running' };
      }
      const state = getPendingAuthState(backend, profileName);
      if (!state) {
        return { ok: false, message: 'No in-flight OAuth flow for this backend/profile' };
      }
      try {
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/exchange-code`, {
          method: 'POST',
          headers: { ...desktopSecretHeader(), 'content-type': 'application/json' },
          body: JSON.stringify({ code, state }),
        });
        if (resp.ok) {
          clearPendingAuthState(backend, profileName);
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

  ipcMain.handle(
    'backends:exchangeOAuthConnectionCode',
    async (
      event,
      backend: string,
      connectionId: string,
      code: string,
    ): Promise<ExchangeCodeResult> => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, message: `invalid backend name: ${backend}` };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, message: 'invalid connection id' };
      }

      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, message: 'SF server is not running' };
      }
      const state = getPendingConnectionAuthState(backend, connectionId);
      if (!state) {
        return { ok: false, message: 'No in-flight OAuth flow for this connection' };
      }
      try {
        const resp = await fetch(`${sfBaseUrl}/${backend}/auth/exchange-code`, {
          method: 'POST',
          headers: { ...desktopSecretHeader(), 'content-type': 'application/json' },
          body: JSON.stringify({ code, state }),
        });
        if (resp.ok) {
          clearPendingConnectionAuthState(backend, connectionId);
          return { ok: true };
        }
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
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
      const resp = await fetch(`${sfBaseUrl}/${backend}/auth/profiles`, {
        headers: desktopSecretHeader(),
      });
      if (!resp.ok) {
        return { profiles: [], error: 'gateway_unreachable' };
      }
      const body = (await resp.json()) as { profiles?: unknown[] };
      return { profiles: body.profiles ?? [] };
    } catch {
      return { profiles: [], error: 'gateway_unreachable' };
    }
  });

  ipcMain.handle('backends:listConnections', async (event, backend: string) => {
    requireTrustedIpcSender(event);
    if (!isSafeBackendName(backend)) {
      return { connections: [], error: 'invalid_backend' };
    }

    const sfBaseUrl = backendStatusService.getServerUrl();
    if (!sfBaseUrl) {
      return { connections: [], error: 'gateway_unreachable' };
    }
    try {
      const resp = await fetch(`${sfBaseUrl}/${backend}/auth/connections`, {
        headers: desktopSecretHeader(),
      });
      if (!resp.ok) {
        return { connections: [], error: 'gateway_unreachable' };
      }
      const body = (await resp.json()) as { connections?: unknown[] };
      return { connections: body.connections ?? [] };
    } catch {
      return { connections: [], error: 'gateway_unreachable' };
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
        { method: 'DELETE', headers: desktopSecretHeader() },
      );
      if (resp.status === 204) return { ok: true };
      return { ok: false, status: resp.status };
    } catch {
      return { ok: false, status: 0 };
    }
  });

  ipcMain.handle(
    'backends:deleteConnection',
    async (event, backend: string, connectionId: string) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400 };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, status: 400 };
      }

      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0 };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/connections/${encodeURIComponent(connectionId)}`,
          {
            method: 'DELETE',
            headers: desktopSecretHeader(),
          },
        );
        if (resp.status === 204) return { ok: true };
        return { ok: false, status: resp.status };
      } catch {
        return { ok: false, status: 0 };
      }
    },
  );

  ipcMain.handle(
    'backends:refreshConnection',
    async (event, backend: string, connectionId: string) => {
      requireTrustedIpcSender(event);
      if (!isSafeBackendName(backend)) {
        return { ok: false, status: 400, message: 'invalid_backend' };
      }
      if (!isSafeOAuthConnectionId(connectionId)) {
        return { ok: false, status: 400, message: 'invalid_connection_id' };
      }

      const sfBaseUrl = backendStatusService.getServerUrl();
      if (!sfBaseUrl) {
        return { ok: false, status: 0, message: 'gateway_unreachable' };
      }
      try {
        const resp = await fetch(
          `${sfBaseUrl}/${backend}/auth/connections/${encodeURIComponent(connectionId)}/refresh`,
          {
            method: 'POST',
            headers: desktopSecretHeader(),
          },
        );
        if (resp.ok) return { ok: true, status: resp.status, connection: await resp.json() };
        return { ok: false, status: resp.status, message: await responseMessage(resp) };
      } catch (e) {
        return { ok: false, status: 0, message: e instanceof Error ? e.message : String(e) };
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

function currentGatewayRedirectPorts(): string[] {
  const status = backendStatusService.getStatus();
  if (!isStatusV2(status)) return [];
  try {
    const url = new URL(status.gateway.url);
    return url.port ? [url.port] : [];
  } catch {
    return [];
  }
}

async function responseMessage(resp: Response): Promise<string | undefined> {
  try {
    const body = (await resp.json()) as { detail?: { code?: string; message?: string } };
    return body.detail?.message ?? body.detail?.code;
  } catch {
    return undefined;
  }
}
