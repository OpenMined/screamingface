import { app, BrowserWindow, ipcMain, session, shell } from 'electron';
import { join } from 'path';
import { is } from '@electron-toolkit/utils';
import { registerAllHandlers } from './ipc';
import { log } from './debug-log';
import { sessionManager } from './services/session-manager';
import { serverProcess } from './services/server-process';
import { isAllowedExternalBrowserUrl, isAllowedPopupUrl } from './services/external-url-policy';
import { requireTrustedIpcSender } from './ipc/sender-validation';

let mainWindow: BrowserWindow | null = null;
let phoenixWindow: BrowserWindow | null = null;

function showMainWindow(reason: string): void {
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.isVisible()) return;
  log(`[main] show window (${reason})`);
  mainWindow.show();
}

function registerMainWindowDiagnostics(window: BrowserWindow): void {
  window.on('ready-to-show', () => {
    log(`[main] ready-to-show`);
  });

  window.on('unresponsive', () => {
    log(`[main] window unresponsive`);
  });

  window.webContents.on('dom-ready', () => {
    log(`[renderer] dom-ready`);
    showMainWindow('dom-ready');
  });

  window.webContents.on('did-finish-load', () => {
    log(`[renderer] did-finish-load`);
  });

  window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    log(
      `[renderer] did-fail-load code=${errorCode} description=${errorDescription} url=${validatedURL}`,
    );
    showMainWindow('did-fail-load');
  });

  window.webContents.on('render-process-gone', (_event, details) => {
    log(`[renderer] render-process-gone reason=${details.reason} exitCode=${details.exitCode}`);
  });

  window.webContents.on('preload-error', (_event, preloadPath, error) => {
    log(`[renderer] preload-error path=${preloadPath} message=${error.message}`);
  });

  window.webContents.on('console-message', (event) => {
    log(
      `[renderer:console:${event.level}] ${event.message} (${event.sourceId}:${event.lineNumber})`,
    );
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 750,
    minWidth: 860,
    minHeight: 600,
    show: false,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#14121a',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
    },
  });

  log(`[main] BrowserWindow created`);
  registerMainWindowDiagnostics(mainWindow);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalBrowserUrl(url)) {
      void shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

function registerPopupHandlers(): void {
  ipcMain.handle('popup:open', (event, url: string, title?: string) => {
    requireTrustedIpcSender(event);
    if (!isAllowedPopupUrl(url)) return;

    // Reuse existing window if still open
    if (phoenixWindow && !phoenixWindow.isDestroyed()) {
      phoenixWindow.loadURL(url);
      phoenixWindow.focus();
      return;
    }

    phoenixWindow = new BrowserWindow({
      width: 1200,
      height: 800,
      minWidth: 600,
      minHeight: 400,
      title: title || 'Debug',
      backgroundColor: '#14121a',
      parent: mainWindow || undefined,
      webPreferences: {
        sandbox: true,
        contextIsolation: true,
      },
    });

    phoenixWindow.loadURL(url);

    phoenixWindow.on('closed', () => {
      phoenixWindow = null;
    });
  });

  ipcMain.handle('popup:close', (event) => {
    requireTrustedIpcSender(event);
    if (phoenixWindow && !phoenixWindow.isDestroyed()) {
      phoenixWindow.close();
      phoenixWindow = null;
    }
  });
}

// Allow renderer fetch() to our local server's self-signed certificate
app.on('certificate-error', (event, _webContents, url, _error, _cert, callback) => {
  const parsed = new URL(url);
  if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
    event.preventDefault();
    callback(true);
  } else {
    callback(false);
  }
});

log(`[main] module loaded`);

app.whenReady().then(() => {
  log(`[main] app.whenReady()`);
  // Accept self-signed certs for local server (covers fetch/XHR in renderer)
  session.defaultSession.setCertificateVerifyProc((request, callback) => {
    if (request.hostname === 'localhost' || request.hostname === '127.0.0.1') {
      callback(0); // accept
    } else {
      callback(-3); // use default verification
    }
  });

  registerAllHandlers();
  registerPopupHandlers();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

let isQuitting = false;
app.on('before-quit', (event) => {
  if (isQuitting) return;
  isQuitting = true;
  event.preventDefault();
  Promise.allSettled([sessionManager.terminateAll(), serverProcess.stop()]).finally(() => {
    app.quit();
  });
});

app.on('window-all-closed', () => {
  // In dev mode, always quit — no reason to linger in the dock when the
  // Vite dev server has stopped. In production, follow macOS convention
  // and keep the app alive for reactivation via the dock icon.
  if (process.platform !== 'darwin' || is.dev) {
    app.quit();
  }
});

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}
