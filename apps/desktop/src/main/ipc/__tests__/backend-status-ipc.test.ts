import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  backendStatusService: {
    authenticate: vi.fn(),
    getServerUrl: vi.fn(() => 'http://127.0.0.1:8001'),
    getPollingError: vi.fn(() => null),
    getStatus: vi.fn(() => ({})),
    logoutGateway: vi.fn(async () => undefined),
    on: vi.fn(),
    refresh: vi.fn(),
  },
  browserWindowGetAllWindows: vi.fn(() => []),
  clearPendingAuthState: vi.fn(),
  clearPendingConnectionAuthState: vi.fn(),
  clearPendingOAuthStates: vi.fn(),
  desktopSecretHeader: vi.fn(() => ({ 'X-SF-Desktop-Secret': 'desktop-secret' })),
  getPendingAuthState: vi.fn(() => null),
  getPendingConnectionAuthState: vi.fn(() => null),
  ipcHandlers: new Map<string, (...args: unknown[]) => unknown>(),
  isSafeBackendName: vi.fn(() => true),
  isSafeOAuthConnectionId: vi.fn(() => true),
  isStatusV2: vi.fn(() => false),
  requireTrustedIpcSender: vi.fn(),
  runOAuthConnectionLauncher: vi.fn(),
  runOAuthLauncher: vi.fn(),
}));

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

vi.mock('../../services/backend-status', () => ({
  backendStatusService: mocks.backendStatusService,
  isStatusV2: mocks.isStatusV2,
}));
vi.mock('../../services/desktop-secret', () => ({
  desktopSecretHeader: mocks.desktopSecretHeader,
}));
vi.mock('../../services/external-url-policy', () => ({
  isSafeBackendName: mocks.isSafeBackendName,
  isSafeOAuthConnectionId: mocks.isSafeOAuthConnectionId,
}));
vi.mock('../../services/oauth-launcher', () => ({
  clearPendingAuthState: mocks.clearPendingAuthState,
  clearPendingConnectionAuthState: mocks.clearPendingConnectionAuthState,
  clearPendingOAuthStates: mocks.clearPendingOAuthStates,
  getPendingAuthState: mocks.getPendingAuthState,
  getPendingConnectionAuthState: mocks.getPendingConnectionAuthState,
  runOAuthConnectionLauncher: mocks.runOAuthConnectionLauncher,
  runOAuthLauncher: mocks.runOAuthLauncher,
}));
vi.mock('../sender-validation', () => ({
  requireTrustedIpcSender: mocks.requireTrustedIpcSender,
}));

import { registerBackendStatusHandlers } from '../backend-status.ipc';

type LauncherResult = { kind: 'failed'; reason: 'cancelled' };

describe('backend status IPC', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.ipcHandlers.clear();
    mocks.backendStatusService.getServerUrl.mockReturnValue('http://127.0.0.1:8001');
    mocks.backendStatusService.getPollingError.mockReturnValue(null);
    mocks.backendStatusService.getStatus.mockReturnValue({});
    mocks.backendStatusService.logoutGateway.mockResolvedValue(undefined);
    mocks.isSafeBackendName.mockReturnValue(true);
    mocks.isSafeOAuthConnectionId.mockReturnValue(true);
    mocks.isStatusV2.mockReturnValue(false);
  });

  it('aborts active OAuth launchers and clears pending state on gateway logout', async () => {
    let resolveProfile: (result: LauncherResult) => void = () => undefined;
    let resolveConnection: (result: LauncherResult) => void = () => undefined;
    mocks.runOAuthLauncher.mockImplementation(
      () => new Promise<LauncherResult>((resolve) => (resolveProfile = resolve)),
    );
    mocks.runOAuthConnectionLauncher.mockImplementation(
      () => new Promise<LauncherResult>((resolve) => (resolveConnection = resolve)),
    );

    registerBackendStatusHandlers();
    const event = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };
    const authenticate = mocks.ipcHandlers.get('backends:authenticateOAuth');
    const authenticateConnection = mocks.ipcHandlers.get('backends:authenticateOAuthConnection');
    const logout = mocks.ipcHandlers.get('backends:logoutGateway');
    if (!authenticate || !authenticateConnection || !logout) {
      throw new Error('backend status handlers were not registered');
    }

    const profilePromise = authenticate(event, 'claude', 'work');
    const connectionPromise = authenticateConnection(event, 'claude', 'work-anthropic');
    const profileSignal = mocks.runOAuthLauncher.mock.calls[0]?.[0]?.abortSignal as AbortSignal;
    const connectionSignal = mocks.runOAuthConnectionLauncher.mock.calls[0]?.[0]
      ?.abortSignal as AbortSignal;

    expect(profileSignal.aborted).toBe(false);
    expect(connectionSignal.aborted).toBe(false);

    await logout(event);

    expect(profileSignal.aborted).toBe(true);
    expect(connectionSignal.aborted).toBe(true);
    expect(mocks.clearPendingOAuthStates).toHaveBeenCalledOnce();
    expect(mocks.backendStatusService.logoutGateway).toHaveBeenCalledOnce();

    resolveProfile({ kind: 'failed', reason: 'cancelled' });
    resolveConnection({ kind: 'failed', reason: 'cancelled' });
    await expect(profilePromise).resolves.toEqual({ kind: 'failed', reason: 'cancelled' });
    await expect(connectionPromise).resolves.toEqual({ kind: 'failed', reason: 'cancelled' });
  });

  it('forwards polling errors to renderer windows', () => {
    const send = vi.fn();
    mocks.browserWindowGetAllWindows.mockReturnValue([{ webContents: { send } }] as never);

    registerBackendStatusHandlers();

    const pollingErrorHandler = mocks.backendStatusService.on.mock.calls.find(
      ([event]) => event === 'pollingError',
    )?.[1];
    if (typeof pollingErrorHandler !== 'function') {
      throw new Error('pollingError handler was not registered');
    }

    const error = {
      status: 401,
      code: 'desktop_secret_invalid',
      message: 'Desktop secret invalid',
      consecutiveFailures: 2,
    };
    pollingErrorHandler(error);

    expect(send).toHaveBeenCalledWith('backends:pollingError', error);
  });
});
