// apps/desktop/src/main/ipc/publish.ipc.ts
//
// IPC for the "Publish to Leaderboard" flow (SF-181 / D-SCORE-006):
//   - publish:getContext  — env/app-version/platform the renderer can't read
//   - publish:submitScore — POST the score from main, exempt from renderer CORS (SF-273)
//   - publish:getLogs / publish:log — backlog + live stream of scoreboard attempts (SF-277)
//   - publish:openExternal — open the leaderboard deep link in the system browser
import { BrowserWindow, ipcMain, shell } from 'electron';
import { resolvePublishContext, type PublishContext } from '../services/publish-context';
import { submitScore } from '../services/publish-score';
import { getPublishLog, onPublishLog } from '../services/publish-log';
import type { PublishOutcome, PublishScoreRequest } from '../../preload/types';
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

  ipcMain.handle(
    'publish:submitScore',
    (event, request: PublishScoreRequest): Promise<PublishOutcome> => {
      requireTrustedIpcSender(event);
      return submitScore(request);
    },
  );

  ipcMain.handle('publish:getLogs', (event): string[] => {
    requireTrustedIpcSender(event);
    return getPublishLog();
  });

  // Stream new publish/scoreboard diagnostic lines to every renderer window.
  onPublishLog((line) => {
    for (const win of BrowserWindow.getAllWindows()) {
      win.webContents.send('publish:log', line);
    }
  });

  ipcMain.handle('publish:openExternal', async (event, url: string): Promise<void> => {
    requireTrustedIpcSender(event);
    // Only ever hand http(s) URLs to the OS — never file://, custom schemes, etc.
    if (!isHttpUrl(url)) return;
    await shell.openExternal(url);
  });
}
