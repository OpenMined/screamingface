import { ipcMain, BrowserWindow } from 'electron';
import https from 'https';
import http from 'http';
import { serverProcess } from '../services/server-process';
import { backendStatusService } from '../services/backend-status';
import { aigwSessionService } from '../services/aigw-session';
import { desktopSecretHeader } from '../services/desktop-secret';
import { isAllowedServerFetchUrl } from '../services/external-url-policy';
import { requireTrustedIpcSender } from './sender-validation';

interface FetchInit {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}

/** Fetch a URL from the main process (bypasses renderer SSL restrictions). */
function nodeFetch(url: string, init?: FetchInit): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const method = init?.method ?? 'GET';
    const req = mod.request(
      url,
      {
        method,
        rejectUnauthorized: false,
        timeout: 5000,
        headers: serverFetchHeaders(init),
      },
      (res) => {
        let data = '';
        res.on('data', (chunk: Buffer) => {
          data += chunk.toString();
        });
        res.on('end', () => resolve({ status: res.statusCode ?? 0, body: data }));
      },
    );
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('timeout'));
    });
    req.on('error', reject);
    if (init?.body) req.write(init.body);
    req.end();
  });
}

function serverFetchHeaders(init?: FetchInit): Record<string, string> {
  const rendererHeaders = Object.fromEntries(
    Object.entries(init?.headers ?? {}).filter(
      ([key]) => key.toLowerCase() !== 'x-sf-desktop-secret',
    ),
  );

  return {
    ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
    ...rendererHeaders,
    ...desktopSecretHeader(),
  };
}

export function registerServerHandlers(): void {
  ipcMain.handle('server:start', (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.start();
  });

  ipcMain.handle('server:stop', (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.stop();
  });

  ipcMain.handle('server:restart', (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.restart();
  });

  ipcMain.handle('server:getStatus', (event) => {
    requireTrustedIpcSender(event);
    return serverProcess.getStatus();
  });

  // Proxy fetch through main process to bypass self-signed cert issues
  ipcMain.handle('server:fetch', async (event, url: string, init?: FetchInit) => {
    requireTrustedIpcSender(event);
    const { info } = serverProcess.getStatus();
    if (!info) {
      return { ok: false, status: 503, body: 'server_restarting' };
    }
    if (!isAllowedServerFetchUrl(url, info, init?.method ?? 'GET')) {
      return { ok: false, status: 0, body: '' };
    }

    try {
      const { status, body } = await nodeFetch(url, init);
      return { ok: status >= 200 && status < 300, status, body };
    } catch {
      return { ok: false, status: 0, body: '' };
    }
  });

  // Forward log and status events to all renderer windows
  serverProcess.on('status', (status) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('server:statusChanged', status);
    }

    // Start/stop backend status polling based on server state
    if (status === 'ready') {
      const { info } = serverProcess.getStatus();
      if (info) {
        const host = info.host === '0.0.0.0' ? '127.0.0.1' : info.host;
        const serverUrl = `${info.scheme}://${host}:${info.port}`;
        void aigwSessionService.setServerUrl(serverUrl);
        backendStatusService.start(serverUrl);
      }
    } else if (status === 'stopped' || status === 'error') {
      void aigwSessionService.setServerUrl(null);
      backendStatusService.stop();
    }
  });

  serverProcess.on('log', (line) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('server:log', line);
    }
  });
}
