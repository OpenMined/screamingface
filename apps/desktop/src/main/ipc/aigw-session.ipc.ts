import { BrowserWindow, ipcMain } from 'electron';
import { aigwSessionService } from '../services/aigw-session';
import { backendStatusService, isStatusV2 } from '../services/backend-status';
import { requireTrustedIpcSender } from './sender-validation';

export function registerAigwSessionHandlers(): void {
  ipcMain.handle('aigw-session:get-state', (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.getState();
  });

  ipcMain.handle('aigw-session:get-jwt', async (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.getJwt();
  });

  ipcMain.handle('aigw-session:is-logged-in', (event) => {
    requireTrustedIpcSender(event);
    return aigwSessionService.isLoggedIn();
  });

  ipcMain.handle(
    'aigw-session:login',
    async (
      event,
      username: string,
      password: string,
      options?: { persist?: boolean; allowPlaintextStorage?: boolean },
    ) => {
      requireTrustedIpcSender(event);
      const result = await aigwSessionService.login({ username, password }, options);
      if (result.ok) void backendStatusService.refresh();
      return result;
    },
  );

  ipcMain.handle('aigw-session:logout', async (event) => {
    requireTrustedIpcSender(event);
    const snapshot = await aigwSessionService.logout();
    void backendStatusService.refresh();
    return snapshot;
  });

  ipcMain.handle('aigw-session:set-gateway-url', (event, gatewayUrl: string) => {
    requireTrustedIpcSender(event);
    const snapshot = aigwSessionService.setGatewayUrl(gatewayUrl);
    void backendStatusService.refresh();
    return snapshot;
  });

  aigwSessionService.on('changed', (snapshot) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('aigw-session:changed', snapshot);
    }
  });

  aigwSessionService.on('expired', (snapshot) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('aigw-session:expired', snapshot);
    }
  });

  backendStatusService.on('statusChanged', (status) => {
    if (!isStatusV2(status)) return;
    if (status.gateway.mode !== 'external' || status.action !== 'login_gateway') return;
    void aigwSessionService.ensureLoggedIn();
  });
}
