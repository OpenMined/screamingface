import { ipcMain } from 'electron';
import { configService } from '../services/config-service';
import { broadcastToRenderers } from './broadcast';

export function registerConfigHandlers(): void {
  ipcMain.handle('config:read', () => {
    return configService.read();
  });

  ipcMain.handle('config:write', (_event, config: Record<string, unknown>) => {
    configService.write(config);
  });

  configService.on('changed', (config) => {
    broadcastToRenderers('config:changed', config);
  });

  configService.watch();
}
