import { ipcMain, BrowserWindow } from 'electron';
import { serverProcess } from '../services/server-process';

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
