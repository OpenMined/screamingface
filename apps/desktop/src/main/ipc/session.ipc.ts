import { ipcMain, BrowserWindow } from 'electron';
import { sessionManager, type SessionType } from '../services/session-manager';
import { requireTrustedIpcSender } from './sender-validation';

export function registerSessionHandlers(): void {
  ipcMain.handle('session:pickDir', (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.pickWorkingDir();
  });

  ipcMain.handle(
    'session:create',
    (
      event,
      type: string,
      workingDir: string,
      pluginConfig?: Record<string, Record<string, unknown>>,
    ) => {
      requireTrustedIpcSender(event);
      return sessionManager.createSession(type as SessionType, workingDir, pluginConfig);
    },
  );

  ipcMain.handle('session:list', (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.listSessions();
  });

  ipcMain.handle('session:terminate', (event, id: string) => {
    requireTrustedIpcSender(event);
    return sessionManager.terminateSession(id);
  });

  ipcMain.handle('session:terminateAll', (event) => {
    requireTrustedIpcSender(event);
    return sessionManager.terminateAll();
  });

  ipcMain.handle('session:remove', (event, id: string) => {
    requireTrustedIpcSender(event);
    sessionManager.removeSession(id);
  });

  ipcMain.handle(
    'session:update',
    (
      event,
      id: string,
      workingDir: string,
      pluginConfig?: Record<string, Record<string, unknown>>,
    ) => {
      requireTrustedIpcSender(event);
      return sessionManager.updateSession(id, workingDir, pluginConfig);
    },
  );

  ipcMain.handle('session:restart', (event, id: string) => {
    requireTrustedIpcSender(event);
    return sessionManager.restartSession(id);
  });

  // Forward session state changes to all renderer windows
  sessionManager.on('sessionsChanged', (sessions) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('session:sessionsChanged', sessions);
    }
  });

  sessionManager.on('log', (id, line) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('session:log', id, line);
    }
  });
}
