import { ipcMain } from 'electron';
import https from 'https';
import http from 'http';
import { serverProcess } from '../services/server-process';
import { backendStatusService } from '../services/backend-status';
import { assertValidSender } from './validate-sender';
import { broadcastToRenderers } from './broadcast';

interface FetchInit {
  method?: string;
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
        headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
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

export function registerServerHandlers(): void {
  ipcMain.handle('server:start', (event) => {
    assertValidSender(event.senderFrame);
    return serverProcess.start();
  });

  ipcMain.handle('server:stop', (event) => {
    assertValidSender(event.senderFrame);
    return serverProcess.stop();
  });

  ipcMain.handle('server:restart', (event) => {
    assertValidSender(event.senderFrame);
    return serverProcess.restart();
  });

  ipcMain.handle('server:getStatus', (event) => {
    assertValidSender(event.senderFrame);
    return serverProcess.getStatus();
  });

  // Proxy fetch through main process to bypass self-signed cert issues
  ipcMain.handle('server:fetch', async (event, url: string, init?: FetchInit) => {
    assertValidSender(event.senderFrame);
    if (!isAllowedServerFetchUrl(url)) {
      return { ok: false, status: 403, body: '' };
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
    broadcastToRenderers('server:statusChanged', status);

    // Start/stop backend status polling based on server state
    if (status === 'ready') {
      const { info } = serverProcess.getStatus();
      if (info) {
        const host = info.host === '0.0.0.0' ? '127.0.0.1' : info.host;
        backendStatusService.start(`${info.scheme}://${host}:${info.port}`);
      }
    } else if (status === 'stopped' || status === 'error') {
      backendStatusService.stop();
    }
  });

  serverProcess.on('log', (line) => {
    broadcastToRenderers('server:log', line);
  });
}

function isAllowedServerFetchUrl(url: string): boolean {
  const serverUrl = backendStatusService.getServerUrl();
  if (!serverUrl) return false;
  try {
    const parsed = new URL(url);
    const server = new URL(serverUrl);
    if (parsed.origin !== server.origin) return false;
    return ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(parsed.hostname);
  } catch {
    return false;
  }
}
