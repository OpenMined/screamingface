import { ipcMain, BrowserWindow } from 'electron';
import { sessionManager } from '../services/session-manager';

export function registerSessionHandlers(): void {
  ipcMain.handle('session:pickDir', () => {
    return sessionManager.pickWorkingDir();
  });

  ipcMain.handle(
    'session:create',
    (_event, type: string, workingDir: string, pluginConfig?: Record<string, Record<string, unknown>>) => {
      return sessionManager.createSession(
        type as 'claude' | 'codex' | 'gemini' | 'claude-desktop',
        workingDir,
        pluginConfig,
      );
    },
  );

  ipcMain.handle('session:list', () => {
    return sessionManager.listSessions();
  });

  ipcMain.handle('session:terminate', (_event, id: string) => {
    return sessionManager.terminateSession(id);
  });

  ipcMain.handle('session:terminateAll', () => {
    return sessionManager.terminateAll();
  });

  ipcMain.handle('session:remove', (_event, id: string) => {
    sessionManager.removeSession(id);
  });

  ipcMain.handle(
    'session:update',
    (_event, id: string, workingDir: string, pluginConfig?: Record<string, Record<string, unknown>>) => {
      return sessionManager.updateSession(id, workingDir, pluginConfig);
    },
  );

  ipcMain.handle('session:restart', (_event, id: string) => {
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
