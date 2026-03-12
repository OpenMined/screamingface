import { ipcMain, BrowserWindow } from 'electron';
import https from 'https';
import http from 'http';
import { serverProcess } from '../services/server-process';

/** Fetch a URL from the main process (bypasses renderer SSL restrictions). */
function nodeFetch(url: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, { rejectUnauthorized: false, timeout: 5000 }, (res) => {
      let data = '';
      res.on('data', (chunk: Buffer) => {
        data += chunk.toString();
      });
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: data }));
    });
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('timeout'));
    });
    req.on('error', reject);
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
  ipcMain.handle('server:fetch', async (_event, url: string) => {
    try {
      const { status, body } = await nodeFetch(url);
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
