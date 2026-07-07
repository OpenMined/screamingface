// apps/desktop/src/main/ipc/leaderboard.ipc.ts
//
// IPC for reading the public leaderboard (OME-321):
//   - leaderboard:getLeaderboard — ranked leaderboard for a benchmark, fetched
//     from main (exempt from renderer CORS, same rationale as publish.ipc.ts).
//
// Deliberately its own file, not folded into publish.ipc.ts: that file's scope
// is the write/publish flow (SF-181/D-SCORE-006); this is an unrelated read
// surface, so it gets its own bounded IPC namespace.

import { ipcMain } from 'electron';
import { listLeaderboard } from '../services/fetch-leaderboard';
import type { LeaderboardData } from '../../preload/types';
import { requireTrustedIpcSender } from './sender-validation';

export function registerLeaderboardHandlers(): void {
  ipcMain.handle(
    'leaderboard:getLeaderboard',
    (event, benchmarkId: string, top?: number): Promise<LeaderboardData | null> => {
      requireTrustedIpcSender(event);
      return listLeaderboard(benchmarkId, top);
    },
  );
}
