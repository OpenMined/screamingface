import { app, BrowserWindow, ipcMain, session, shell } from 'electron';
import { join } from 'path';
import { is } from '@electron-toolkit/utils';
import { registerAllHandlers } from './ipc';
import { log } from './debug-log';
import { sessionManager } from './services/session-manager';

let mainWindow: BrowserWindow | null = null;
let phoenixWindow: BrowserWindow | null = null;

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

  mainWindow.on('ready-to-show', () => {
    log(`[main] ready-to-show`);
    mainWindow?.show();
    // Temporary: open DevTools in production to diagnose Finder-launch black screen
    mainWindow?.webContents.openDevTools({ mode: 'detach' });
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

function registerPopupHandlers(): void {
  ipcMain.handle('popup:open', (_event, url: string, title?: string) => {
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

  ipcMain.handle('popup:close', () => {
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
  sessionManager.terminateAll().finally(() => {
    app.quit();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}
