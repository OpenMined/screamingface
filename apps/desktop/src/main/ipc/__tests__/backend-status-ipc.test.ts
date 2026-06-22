import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

  describe('setProfileApiKey', () => {
    const event = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };

    const getHandler = () => {
      registerBackendStatusHandlers();
      const handler = mocks.ipcHandlers.get('backends:setProfileApiKey');
      if (!handler) throw new Error('setProfileApiKey handler was not registered');
      return handler;
    };

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('PUTs the key to the SF auth proxy with the desktop secret', async () => {
      const fetchMock = vi.fn(async () => ({ ok: true, status: 200 }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: true });
      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8001/claude/auth/profiles/work/api-key',
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'X-SF-Desktop-Secret': 'desktop-secret',
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({ api_key: 'sk-ant-api03-xyz-1234' }),
        }),
      );
    });

    it('surfaces the gateway error detail on failure', async () => {
      const fetchMock = vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({ detail: { code: 'api_key_not_supported' } }),
      }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'codex', 'work', 'sk-proj-xyz-1234');

      expect(result).toEqual({ ok: false, status: 400, message: 'api_key_not_supported' });
    });

    it('rejects too-short keys without touching the network', async () => {
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'abc');

      expect(result).toEqual({
        ok: false,
        status: 400,
        message: 'API key is missing or too short',
      });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects unsafe backend names', async () => {
      mocks.isSafeBackendName.mockReturnValue(false);
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, '../evil', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: false, status: 400, message: 'invalid backend name' });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('reports a missing SF server without touching the network', async () => {
      mocks.backendStatusService.getServerUrl.mockReturnValue(null);
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: false, status: 0, message: 'SF server is not running' });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('maps a network failure to gateway unreachable', async () => {
      const fetchMock = vi.fn(async () => {
        throw new Error('ECONNREFUSED');
      });
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: false, status: 0, message: 'gateway unreachable' });
    });

    it('falls back to status-only when the error body is not JSON', async () => {
      const fetchMock = vi.fn(async () => ({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        },
      }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: false, status: 500, message: undefined });
    });
  });

  describe('createConnectionApiKey', () => {
    const event = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };

    const getHandler = () => {
      registerBackendStatusHandlers();
      const handler = mocks.ipcHandlers.get('backends:createConnectionApiKey');
      if (!handler) throw new Error('createConnectionApiKey handler was not registered');
      return handler;
    };

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('POSTs label + key to the connections api-key proxy', async () => {
      const fetchMock = vi.fn(async () => ({ ok: true, status: 201 }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: true });
      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8001/claude/auth/connections/api-key',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'X-SF-Desktop-Secret': 'desktop-secret',
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify({ api_key: 'sk-ant-api03-xyz-1234', label: 'work' }),
        }),
      );
    });

    it('omits the label when none is provided', async () => {
      const fetchMock = vi.fn(async () => ({ ok: true, status: 201 }));
      vi.stubGlobal('fetch', fetchMock);

      await getHandler()(event, 'gemini', undefined, 'sk-gemini-xyz-1234');

      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8001/gemini/auth/connections/api-key',
        expect.objectContaining({ body: JSON.stringify({ api_key: 'sk-gemini-xyz-1234' }) }),
      );
    });

    it('surfaces the gateway error code on failure', async () => {
      const fetchMock = vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({ detail: { code: 'api_key_not_supported' } }),
      }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'codex', 'cdx', 'sk-proj-xyz-1234');

      expect(result).toEqual({ ok: false, status: 400, message: 'api_key_not_supported' });
    });

    it('surfaces the first error from an array-shaped 422 detail', async () => {
      // FastAPI validation errors (incl. the redacted ones) return detail as an
      // array; the message must be actionable, not a bare status (SF-291 R3-4).
      const fetchMock = vi.fn(async () => ({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            {
              type: 'string_pattern_mismatch',
              loc: ['body', 'label'],
              msg: 'String should match pattern',
            },
          ],
        }),
      }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'bad#label', 'sk-ant-api03-xyz-1234');

      expect(result).toEqual({ ok: false, status: 422, message: 'String should match pattern' });
    });

    it('rejects too-short keys without touching the network', async () => {
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'work', 'abc');

      expect(result).toEqual({
        ok: false,
        status: 400,
        message: 'API key is missing or too short',
      });
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  describe('setConnectionApiKey', () => {
    const event = { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } };
    const cid = '11111111-1111-1111-1111-111111111111';

    const getHandler = () => {
      registerBackendStatusHandlers();
      const handler = mocks.ipcHandlers.get('backends:setConnectionApiKey');
      if (!handler) throw new Error('setConnectionApiKey handler was not registered');
      return handler;
    };

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('PUTs the new key to the connection api-key proxy', async () => {
      const fetchMock = vi.fn(async () => ({ ok: true, status: 200 }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', cid, 'sk-ant-api03-rotated-key');

      expect(result).toEqual({ ok: true });
      expect(fetchMock).toHaveBeenCalledWith(
        `http://127.0.0.1:8001/claude/auth/connections/${cid}/api-key`,
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ api_key: 'sk-ant-api03-rotated-key' }),
        }),
      );
    });

    it('rejects an unsafe connection id without touching the network', async () => {
      mocks.isSafeOAuthConnectionId.mockReturnValue(false);
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      const result = await getHandler()(event, 'claude', 'bad id', 'sk-ant-api03-rotated-key');

      expect(result).toEqual({ ok: false, status: 400, message: 'invalid connection id' });
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
