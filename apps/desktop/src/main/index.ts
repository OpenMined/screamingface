import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { join } from 'path';
import { is } from '@electron-toolkit/utils';
import { registerAllHandlers } from './ipc';

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

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show();
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

app.whenReady().then(() => {
  registerAllHandlers();
  registerPopupHandlers();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
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
