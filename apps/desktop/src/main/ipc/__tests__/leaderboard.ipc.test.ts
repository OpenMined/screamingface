import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  ipcHandlers: new Map<string, (...args: unknown[]) => unknown>(),
  listLeaderboard: vi.fn(),
  requireTrustedIpcSender: vi.fn(),
}));

vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, handler: (...args: unknown[]) => unknown) => {
      mocks.ipcHandlers.set(channel, handler);
    },
  },
}));
vi.mock('../../services/fetch-leaderboard', () => ({
  listLeaderboard: mocks.listLeaderboard,
}));
vi.mock('../sender-validation', () => ({
  requireTrustedIpcSender: mocks.requireTrustedIpcSender,
}));

import { registerLeaderboardHandlers } from '../leaderboard.ipc';

const EVENT = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };

describe('leaderboard IPC', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.ipcHandlers.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('registers leaderboard:getLeaderboard', () => {
    registerLeaderboardHandlers();
    expect(mocks.ipcHandlers.has('leaderboard:getLeaderboard')).toBe(true);
  });

  it('validates the sender before delegating to listLeaderboard', async () => {
    mocks.listLeaderboard.mockResolvedValue({ benchmark: { id: 'livetruth' }, entries: [] });
    registerLeaderboardHandlers();

    const handler = mocks.ipcHandlers.get('leaderboard:getLeaderboard');
    if (!handler) throw new Error('leaderboard:getLeaderboard was not registered');

    const out = await handler(EVENT, 'livetruth', 10);

    expect(mocks.requireTrustedIpcSender).toHaveBeenCalledWith(EVENT);
    expect(mocks.listLeaderboard).toHaveBeenCalledWith('livetruth', 10);
    expect(out).toEqual({ benchmark: { id: 'livetruth' }, entries: [] });
  });

  it('propagates a null result (unknown benchmark / unreachable scoreboard) without throwing', async () => {
    mocks.listLeaderboard.mockResolvedValue(null);
    registerLeaderboardHandlers();

    const handler = mocks.ipcHandlers.get('leaderboard:getLeaderboard');
    if (!handler) throw new Error('leaderboard:getLeaderboard was not registered');

    expect(await handler(EVENT, 'unknown-benchmark')).toBeNull();
  });
});
