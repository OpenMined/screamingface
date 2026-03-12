import { ipcMain, BrowserWindow } from 'electron';
import { configService } from '../services/config-service';

export function registerConfigHandlers(): void {
  ipcMain.handle('config:read', () => {
    return configService.read();
  });

  ipcMain.handle('config:write', (_event, config: Record<string, unknown>) => {
    configService.write(config);
  });

  configService.on('changed', (config) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('config:changed', config);
    }
  });

  configService.watch();
}
