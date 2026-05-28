import { describe, expect, it, vi } from 'vitest';
import { EventEmitter } from 'events';

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => '/tmp/sf-user-data'),
    getAppPath: vi.fn(() => '/repo/apps/desktop'),
  },
  dialog: {},
  BrowserWindow: {},
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));

const spawnMock = vi.fn();
vi.mock('child_process', () => ({
  spawn: (...args: unknown[]) => spawnMock(...args),
  execFile: vi.fn(),
  ChildProcess: class {},
}));

vi.mock('../config-service', () => ({
  configService: {
    serverDir: '/repo/apps/server',
    read: () => ({
      version: '0.1.0',
      server: { host: '127.0.0.1', port: 8000, ssl: false },
      plugin_config: {},
    }),
  },
}));

vi.mock('../backend-status', () => ({
  backendStatusService: { getServerUrl: () => 'http://127.0.0.1:8000' },
}));

const SECRET_PATH = '/tmp/sf-user-data/.sf/runtime/desktop.secret';
vi.mock('../desktop-secret', () => ({
  getDesktopSecretPath: () => SECRET_PATH,
}));

import { frontendPluginNameForSession, sessionManager } from '../session-manager';

describe('session-manager frontend plugin mapping', () => {
  it('uses provider-specific frontend plugins for session types', () => {
    expect(frontendPluginNameForSession('claude')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('claude-desktop')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('codex')).toBe('codex-frontend');
    expect(frontendPluginNameForSession('gemini')).toBe('gemini-frontend');
  });
});

function makeFakeChild(): EventEmitter & { stdout: EventEmitter; stderr: EventEmitter } {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
  };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

describe('session-manager proxy spawn env', () => {
  it('forwards SF_DESKTOP_SECRET_FILE so the proxy can auth to /ensemble', async () => {
    // Regression: the per-session proxy was spawned with env { ...process.env },
    // which lacks SF_DESKTOP_SECRET_FILE -> its url4 resolver sent no desktop
    // secret -> the main server's secret-protected /ensemble returned 401.
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);
    // Avoid real port binding.
    (
      sessionManager as unknown as { allocateRandomPort: () => Promise<number> }
    ).allocateRandomPort = vi.fn().mockResolvedValue(12345);

    const session = {
      id: 'sess-1',
      type: 'claude',
      port: 9101,
      status: 'starting',
      createdAt: new Date(),
      workingDir: '/tmp',
      pluginConfig: {},
      proxy: null,
      proxyReady: null,
      scriptPath: null,
    };

    const pending = (
      sessionManager as unknown as { spawnProxy: (s: unknown) => Promise<void> }
    ).spawnProxy(session);

    // Wait until spawn fires (spawnProxy awaits port allocation first), then
    // signal the proxy as ready so the promise resolves.
    await vi.waitFor(() => expect(spawnMock).toHaveBeenCalledTimes(1));
    child.stdout.emit('data', Buffer.from(JSON.stringify({ event: 'ready', port: 9101 }) + '\n'));
    await pending;

    const spawnOptions = spawnMock.mock.calls[0][2] as { env: Record<string, string> };
    expect(spawnOptions.env.SF_DESKTOP_SECRET_FILE).toBe(SECRET_PATH);
  });
});
