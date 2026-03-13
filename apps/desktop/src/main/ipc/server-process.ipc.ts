import { ipcMain, BrowserWindow } from 'electron';
import https from 'https';
import http from 'http';
import { serverProcess } from '../services/server-process';

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
  ipcMain.handle('server:start', () => {
    return serverProcess.start();
  });

  ipcMain.handle('server:stop', () => {
    return serverProcess.stop();
  });

  ipcMain.handle('server:restart', () => {
    return serverProcess.restart();
  });

  ipcMain.handle('server:getStatus', () => {
    return serverProcess.getStatus();
  });

  // Proxy fetch through main process to bypass self-signed cert issues
  ipcMain.handle('server:fetch', async (_event, url: string, init?: FetchInit) => {
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
  });

  serverProcess.on('log', (line) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('server:log', line);
    }
  });
}
