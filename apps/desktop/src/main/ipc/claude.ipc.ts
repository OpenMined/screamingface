import { ipcMain } from 'electron';
import { execFile } from 'child_process';

export function registerClaudeHandlers(): void {
  ipcMain.handle('claude:launch', (_event, baseUrl: string) => {
    const cmd = `export ANTHROPIC_BASE_URL=${baseUrl} && claude`;
    execFile('osascript', [
      '-e',
      `tell application "Terminal" to do script "${cmd}"`,
    ]);
  });
}
