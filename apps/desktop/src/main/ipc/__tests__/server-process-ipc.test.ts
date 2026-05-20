import { EventEmitter } from 'events';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  backendStatusService: {
    start: vi.fn(),
    stop: vi.fn(),
  },
  browserWindowGetAllWindows: vi.fn(() => []),
  desktopSecretHeader: vi.fn(() => ({ 'X-SF-Desktop-Secret': 'desktop-secret' })),
  httpRequest: vi.fn(),
  httpsRequest: vi.fn(),
  ipcHandlers: new Map<string, (...args: unknown[]) => unknown>(),
  isAllowedServerFetchUrl: vi.fn(() => true),
  requireTrustedIpcSender: vi.fn(),
  serverProcess: {
    getStatus: vi.fn(),
    on: vi.fn(),
    restart: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  },
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

vi.mock('http', () => ({ default: { request: mocks.httpRequest }, request: mocks.httpRequest }));
vi.mock('https', () => ({ default: { request: mocks.httpsRequest }, request: mocks.httpsRequest }));
vi.mock('../../services/backend-status', () => ({
  backendStatusService: mocks.backendStatusService,
}));
vi.mock('../../services/desktop-secret', () => ({
  desktopSecretHeader: mocks.desktopSecretHeader,
}));
vi.mock('../../services/external-url-policy', () => ({
  isAllowedServerFetchUrl: mocks.isAllowedServerFetchUrl,
}));
vi.mock('../../services/server-process', () => ({ serverProcess: mocks.serverProcess }));
vi.mock('../sender-validation', () => ({
  requireTrustedIpcSender: mocks.requireTrustedIpcSender,
}));

import { registerServerHandlers } from '../server-process.ipc';

describe('server process IPC', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.ipcHandlers.clear();
    mocks.isAllowedServerFetchUrl.mockReturnValue(true);
    mocks.desktopSecretHeader.mockReturnValue({ 'X-SF-Desktop-Secret': 'desktop-secret' });
    mocks.serverProcess.getStatus.mockReturnValue({
      status: 'ready',
      info: { event: 'ready', host: '127.0.0.1', pid: 123, port: 8001, scheme: 'http' },
    });
  });

  it('forces renderer server.fetch through main-process Desktop secret injection', async () => {
    const capturedRequests: Array<{
      options: { headers?: Record<string, string> };
      url: string;
    }> = [];
    mocks.httpRequest.mockImplementation(
      (
        url: string,
        options: { headers?: Record<string, string> },
        onResponse: (response: EventEmitter & { statusCode: number }) => void,
      ) => {
        capturedRequests.push({ url, options });
        const response = new EventEmitter() as EventEmitter & { statusCode: number };
        response.statusCode = 200;
        queueMicrotask(() => {
          onResponse(response);
          response.emit('data', Buffer.from('ok'));
          response.emit('end');
        });
        return {
          destroy: vi.fn(),
          end: vi.fn(),
          on: vi.fn(),
          write: vi.fn(),
        };
      },
    );

    registerServerHandlers();
    const handler = mocks.ipcHandlers.get('server:fetch');
    if (!handler) throw new Error('server:fetch handler was not registered');

    const result = await handler(
      { senderFrame: { url: 'file:///Applications/ScreamingFace.app/index.html' } },
      'http://127.0.0.1:8001/ensemble',
      {
        headers: {
          Accept: 'text/plain',
          'X-SF-Desktop-Secret': 'renderer-secret',
          'x-sf-desktop-secret': 'renderer-secret-lowercase',
        },
      },
    );

    expect(result).toEqual({ ok: true, status: 200, body: 'ok' });
    expect(mocks.requireTrustedIpcSender).toHaveBeenCalledOnce();
    expect(capturedRequests).toHaveLength(1);
    expect(capturedRequests[0].url).toBe('http://127.0.0.1:8001/ensemble');
    expect(capturedRequests[0].options.headers).toMatchObject({
      Accept: 'text/plain',
      'X-SF-Desktop-Secret': 'desktop-secret',
    });
    expect(capturedRequests[0].options.headers?.['x-sf-desktop-secret']).toBeUndefined();
  });
});
