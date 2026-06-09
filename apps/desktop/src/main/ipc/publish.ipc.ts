// apps/desktop/src/main/ipc/publish.ipc.ts
//
// IPC for the "Publish to Leaderboard" flow (SF-181 / D-SCORE-006):
//   - publish:getContext  — env/app-version/platform the renderer can't read
//   - publish:openExternal — open the leaderboard deep link in the system browser
import { ipcMain, shell } from 'electron';
import { resolvePublishContext, type PublishContext } from '../services/publish-context';
import { requireTrustedIpcSender } from './sender-validation';

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

export function registerPublishHandlers(): void {
  ipcMain.handle('publish:getContext', (event): PublishContext => {
    requireTrustedIpcSender(event);
    return resolvePublishContext();
  });

  ipcMain.handle('publish:openExternal', async (event, url: string): Promise<void> => {
    requireTrustedIpcSender(event);
    // Only ever hand http(s) URLs to the OS — never file://, custom schemes, etc.
    if (!isHttpUrl(url)) return;
    await shell.openExternal(url);
  });
}
