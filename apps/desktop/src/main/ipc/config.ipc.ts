import { ipcMain, BrowserWindow } from 'electron';
import { configService } from '../services/config-service';
import { requireTrustedIpcSender } from './sender-validation';

export function registerConfigHandlers(): void {
  ipcMain.handle('config:read', (event) => {
    requireTrustedIpcSender(event);
    return configService.read();
  });

  ipcMain.handle('config:write', (event, config: Record<string, unknown>) => {
    requireTrustedIpcSender(event);
    configService.write(config);
  });

  configService.on('changed', (config) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('config:changed', config);
    }
  });

  configService.watch();
}
