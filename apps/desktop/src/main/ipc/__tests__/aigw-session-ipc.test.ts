import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const listeners = new Map<string, Array<(...args: unknown[]) => void>>();
  const aigwSessionService = {
    getState: vi.fn(),
    getJwt: vi.fn(),
    ensureLoggedIn: vi.fn(),
    isLoggedIn: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    setGatewayUrl: vi.fn(),
    on: vi.fn((event: string, listener: (...args: unknown[]) => void) => {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
      return aigwSessionService;
    }),
    emit: vi.fn((event: string, ...args: unknown[]) => {
      for (const listener of listeners.get(event) ?? []) listener(...args);
      return true;
    }),
    removeAllListeners: vi.fn(() => {
      listeners.clear();
      return aigwSessionService;
    }),
  };
  return {
    aigwSessionService,
    backendStatusService: {
      on: vi.fn(),
      refresh: vi.fn(),
    },
    browserWindowGetAllWindows: vi.fn(() => []),
    ipcHandlers: new Map<string, (...args: unknown[]) => unknown>(),
    requireTrustedIpcSender: vi.fn(),
  };
});

vi.mock('electron', () => ({
  BrowserWindow: {
    getAllWindows: mocks.browserWindowGetAllWindows,
  },
  ipcMain: {
    handle: (channel: string, handler: (...args: unknown[]) => unknown) => {
      mocks.ipcHandlers.set(channel, handler);
    },
  },
}));

vi.mock('../../services/aigw-session', () => ({
  aigwSessionService: mocks.aigwSessionService,
}));
vi.mock('../../services/backend-status', () => ({
  backendStatusService: mocks.backendStatusService,
  isStatusV2: vi.fn(
    (value: unknown) =>
      typeof value === 'object' && value !== null && (value as { version?: unknown }).version === 2,
  ),
}));
vi.mock('../sender-validation', () => ({
  requireTrustedIpcSender: mocks.requireTrustedIpcSender,
}));

import { registerAigwSessionHandlers } from '../aigw-session.ipc';

const snapshot = {
  hasValidJwt: true,
  jwtExpiresAt: '2026-01-01T01:00:00.000Z',
  isLoggedIn: true,
  username: 'admin',
  gatewayUrl: 'http://gateway',
  rememberAvailable: true,
  storedInPlaintext: false,
  lastError: null,
};

describe('AIGateway session IPC', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.ipcHandlers.clear();
    mocks.aigwSessionService.removeAllListeners();
    mocks.aigwSessionService.getState.mockReturnValue(snapshot);
    mocks.aigwSessionService.getJwt.mockResolvedValue('jwt-token');
    mocks.aigwSessionService.ensureLoggedIn.mockResolvedValue('jwt-token');
    mocks.aigwSessionService.isLoggedIn.mockReturnValue(true);
    mocks.aigwSessionService.login.mockResolvedValue({ ok: true, snapshot });
    mocks.aigwSessionService.logout.mockResolvedValue({ ...snapshot, isLoggedIn: false });
    mocks.aigwSessionService.setGatewayUrl.mockReturnValue({
      ...snapshot,
      gatewayUrl: 'https://gateway.example.com',
    });
  });

  it('registers trusted handlers and refreshes backend status after login/logout', async () => {
    registerAigwSessionHandlers();
    const event = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };

    const login = mocks.ipcHandlers.get('aigw-session:login');
    const logout = mocks.ipcHandlers.get('aigw-session:logout');
    if (!login || !logout) throw new Error('AIGateway session handlers were not registered');

    await expect(login(event, 'admin', 'test123', { persist: false })).resolves.toEqual({
      ok: true,
      snapshot,
    });
    await expect(logout(event)).resolves.toMatchObject({ isLoggedIn: false });

    expect(mocks.requireTrustedIpcSender).toHaveBeenCalledTimes(2);
    expect(mocks.aigwSessionService.login).toHaveBeenCalledWith(
      { username: 'admin', password: 'test123' },
      { persist: false },
    );
    expect(mocks.aigwSessionService.logout).toHaveBeenCalledOnce();
    expect(mocks.backendStatusService.refresh).toHaveBeenCalledTimes(2);
  });

  it('does not refresh backend status after failed login', async () => {
    mocks.aigwSessionService.login.mockResolvedValueOnce({
      ok: false,
      message: 'invalid',
      snapshot: { ...snapshot, isLoggedIn: false },
    });
    registerAigwSessionHandlers();
    const login = mocks.ipcHandlers.get('aigw-session:login');
    if (!login) throw new Error('login handler was not registered');

    await expect(login({}, 'admin', 'bad')).resolves.toMatchObject({ ok: false });

    expect(mocks.backendStatusService.refresh).not.toHaveBeenCalled();
  });

  it('forwards changed and expired snapshots to renderer windows without a JWT', () => {
    const send = vi.fn();
    mocks.browserWindowGetAllWindows.mockReturnValue([{ webContents: { send } }] as never);
    registerAigwSessionHandlers();

    mocks.aigwSessionService.emit('changed', snapshot);
    mocks.aigwSessionService.emit('expired', { ...snapshot, isLoggedIn: false });

    expect(send).toHaveBeenCalledWith('aigw-session:changed', snapshot);
    expect(send).toHaveBeenCalledWith('aigw-session:expired', { ...snapshot, isLoggedIn: false });
    expect(Object.hasOwn(snapshot, 'jwt')).toBe(false);
  });

  it('tries silent login when backend status reports login_gateway', () => {
    registerAigwSessionHandlers();

    const statusChanged = mocks.backendStatusService.on.mock.calls.find(
      ([event]) => event === 'statusChanged',
    )?.[1];
    if (typeof statusChanged !== 'function') {
      throw new Error('statusChanged handler was not registered');
    }

    statusChanged({
      version: 2,
      gateway: {
        mode: 'external',
        managed_by_runner: false,
        reachable: true,
        authenticated: false,
        auth_required: true,
        url: 'https://gateway.example.com',
      },
      action: 'login_gateway',
    });

    expect(mocks.aigwSessionService.ensureLoggedIn).toHaveBeenCalledOnce();
  });
});
