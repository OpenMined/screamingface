// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import type { BackendStatusResponse, ServerStatus } from '../../preload/types';

const logListeners: Array<(line: string) => void> = [];
const statusListeners: Array<(status: ServerStatus) => void> = [];

const serverStart = vi.fn(async () => true);
const serverStop = vi.fn(async () => undefined);
const serverRestart = vi.fn(async () => undefined);
const getServerStatus = vi.fn(async () => ({
  status: 'ready' as const,
  info: { event: 'ready' as const, host: '127.0.0.1', port: 8001, pid: 123, scheme: 'http' },
}));

const getBackendStatus = vi.fn(async (): Promise<BackendStatusResponse> => ({}));
const getBackendPollingError = vi.fn(async () => null);

(window as unknown as { electronAPI: unknown }).electronAPI = {
  popup: {
    open: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
  },
  server: {
    start: serverStart,
    stop: serverStop,
    restart: serverRestart,
    getStatus: getServerStatus,
    onStatusChanged: (callback: (status: ServerStatus) => void) => {
      statusListeners.push(callback);
      return () => {
        const index = statusListeners.indexOf(callback);
        if (index >= 0) statusListeners.splice(index, 1);
      };
    },
    onLog: (callback: (line: string) => void) => {
      logListeners.push(callback);
      return () => {
        const index = logListeners.indexOf(callback);
        if (index >= 0) logListeners.splice(index, 1);
      };
    },
    fetch: vi.fn(async () => ({ ok: true, status: 200, body: '{}' })),
  },
  venv: {
    detect: vi.fn(async () => ({
      status: 'ready' as const,
      uvFound: true,
      needsSync: false,
      autoBootstrap: false,
    })),
    create: vi.fn(async () => true),
    sync: vi.fn(async () => true),
    listPackages: vi.fn(async () => []),
    onStatusChanged: vi.fn(() => () => undefined),
    onProgress: vi.fn(() => () => undefined),
  },
  plugins: {
    list: vi.fn(async () => []),
    install: vi.fn(),
    uninstall: vi.fn(),
    activate: vi.fn(),
    deactivate: vi.fn(),
    getCatalog: vi.fn(async () => []),
    discover: vi.fn(async () => ({})),
    onChanged: vi.fn(() => () => undefined),
  },
  config: {
    read: vi.fn(async () => ({ plugins: [] })),
    write: vi.fn(async () => undefined),
    onChanged: vi.fn(() => () => undefined),
  },
  backends: {
    getStatus: getBackendStatus,
    getPollingError: getBackendPollingError,
    refresh: getBackendStatus,
    authenticate: vi.fn(async () => undefined),
    loginGateway: vi.fn(async () => ({ ok: true })),
    logoutGateway: vi.fn(async () => undefined),
    authenticateOAuth: vi.fn(async () => ({ kind: 'complete' as const })),
    authenticateOAuthConnection: vi.fn(async () => ({ kind: 'complete' as const })),
    listProfiles: vi.fn(async () => ({ profiles: [] })),
    deleteProfile: vi.fn(async () => ({ ok: true })),
    listConnections: vi.fn(async () => ({ connections: [] })),
    deleteConnection: vi.fn(async () => ({ ok: true })),
    refreshConnection: vi.fn(async () => ({ ok: true })),
    getPendingAuthState: vi.fn(async () => null),
    getPendingConnectionAuthState: vi.fn(async () => null),
    exchangeOAuthCode: vi.fn(async () => ({ ok: true })),
    exchangeOAuthConnectionCode: vi.fn(async () => ({ ok: true })),
    onStatusChanged: vi.fn(() => () => undefined),
    onPollingError: vi.fn(() => () => undefined),
    onAlert: vi.fn(() => () => undefined),
  },
  aigwSession: {
    getState: vi.fn(async () => ({
      hasValidJwt: false,
      jwtExpiresAt: null,
      isLoggedIn: false,
      username: null,
      gatewayUrl: 'http://127.0.0.1:9105',
      rememberAvailable: true,
      storedInPlaintext: false,
      lastError: null,
    })),
    getJwt: vi.fn(async () => null),
    isLoggedIn: vi.fn(async () => false),
    login: vi.fn(async () => ({
      ok: true,
      snapshot: {
        hasValidJwt: true,
        jwtExpiresAt: '2026-01-01T01:00:00.000Z',
        isLoggedIn: true,
        username: 'admin',
        gatewayUrl: 'http://127.0.0.1:9105',
        rememberAvailable: true,
        storedInPlaintext: false,
        lastError: null,
      },
    })),
    logout: vi.fn(async () => ({
      hasValidJwt: false,
      jwtExpiresAt: null,
      isLoggedIn: false,
      username: null,
      gatewayUrl: 'http://127.0.0.1:9105',
      rememberAvailable: true,
      storedInPlaintext: false,
      lastError: null,
    })),
    setGatewayUrl: vi.fn(async () => ({
      hasValidJwt: false,
      jwtExpiresAt: null,
      isLoggedIn: false,
      username: null,
      gatewayUrl: 'http://127.0.0.1:9105',
      rememberAvailable: true,
      storedInPlaintext: false,
      lastError: null,
    })),
    onChanged: vi.fn(() => () => undefined),
    onExpired: vi.fn(() => () => undefined),
  },
  session: {
    pickDir: vi.fn(),
    create: vi.fn(),
    list: vi.fn(async () => []),
    stop: vi.fn(),
    remove: vi.fn(),
    onStatusChanged: vi.fn(() => () => undefined),
    onLog: vi.fn(() => () => undefined),
  },
};

vi.mock('@/views/SettingsView', () => ({
  SettingsView: () => <div>Settings placeholder</div>,
}));

vi.mock('@/components/server/BackendStatusPanel', () => ({
  BackendStatusPanel: () => <div>Backends placeholder</div>,
}));

import { App } from './App';

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  logListeners.length = 0;
  statusListeners.length = 0;
  serverStart.mockClear();
  serverStop.mockClear();
  serverRestart.mockClear();
  getServerStatus.mockClear();
  getBackendStatus.mockClear();
  getBackendPollingError.mockClear();
});

describe('App server logs', () => {
  it('keeps Dashboard logs after navigating away and back', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy();

    await act(async () => {
      logListeners.forEach((listener) => listener('INFO: server boot complete'));
    });
    expect(await screen.findByText('server boot complete')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Settings/i }));
    expect(await screen.findByText('Settings placeholder')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Dashboard/i }));
    await waitFor(() => expect(screen.getByText('server boot complete')).toBeTruthy());
  });
});
