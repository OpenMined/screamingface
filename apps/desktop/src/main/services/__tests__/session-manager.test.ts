import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (...args: unknown[]) => void;

type MockEmitter = {
  emit: (event: string, ...args: unknown[]) => boolean;
  on: (event: string, listener: Listener) => MockEmitter;
  once: (event: string, listener: Listener) => MockEmitter;
  removeListener: (event: string, listener: Listener) => MockEmitter;
};

type MockChild = MockEmitter & {
  kill: ReturnType<typeof vi.fn>;
  stderr: MockEmitter;
  stdout: MockEmitter;
};

const mocks = vi.hoisted(() => {
  class MockEventEmitter {
    private listeners = new Map<string, Set<Listener>>();

    emit(event: string, ...args: unknown[]): boolean {
      const listeners = [...(this.listeners.get(event) ?? [])];
      for (const listener of listeners) listener(...args);
      return listeners.length > 0;
    }

    on(event: string, listener: Listener): this {
      const listeners = this.listeners.get(event) ?? new Set<Listener>();
      listeners.add(listener);
      this.listeners.set(event, listeners);
      return this;
    }

    once(event: string, listener: Listener): this {
      const wrapper: Listener = (...args) => {
        this.removeListener(event, wrapper);
        listener(...args);
      };
      return this.on(event, wrapper);
    }

    removeListener(event: string, listener: Listener): this {
      this.listeners.get(event)?.delete(listener);
      return this;
    }
  }

  return {
    MockEventEmitter,
    backendStatusService: {
      getServerUrl: vi.fn(() => 'http://127.0.0.1:8000'),
    },
    childProcesses: [] as MockChild[],
    execFile: vi.fn((_cmd: string, _args: string[], cb?: (err?: Error | null) => void) => {
      cb?.(null);
    }),
    existsSync: vi.fn(() => true),
    spawn: vi.fn(),
  };
});

function makeChild(): MockChild {
  const child = new mocks.MockEventEmitter() as MockChild;
  child.stdout = new mocks.MockEventEmitter();
  child.stderr = new mocks.MockEventEmitter();
  child.kill = vi.fn();
  return child;
}

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => '/tmp/sf-user-data'),
    getAppPath: vi.fn(() => '/repo/apps/desktop'),
  },
  dialog: {},
  BrowserWindow: {},
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));
vi.mock('child_process', () => ({
  execFile: mocks.execFile,
  spawn: mocks.spawn,
}));
vi.mock('fs', () => ({
  chmodSync: vi.fn(),
  existsSync: mocks.existsSync,
  mkdirSync: vi.fn(),
  readFileSync: vi.fn(() => ''),
  unlinkSync: vi.fn(),
  writeFileSync: vi.fn(),
}));
vi.mock('crypto', () => ({ randomUUID: vi.fn(() => 'session-1') }));
vi.mock('net', () => {
  class MockSocket extends mocks.MockEventEmitter {
    connect(): void {
      queueMicrotask(() => this.emit('error', new Error('free')));
    }

    destroy(): void {}
  }

  return {
    default: {
      Socket: MockSocket,
      createServer: () => ({
        address: () => ({ port: 18000 }),
        close: (cb: () => void) => cb(),
        listen: (_port: number, _host: string, cb: () => void) => cb(),
        on: vi.fn(),
      }),
    },
  };
});
vi.mock('../backend-status', () => ({ backendStatusService: mocks.backendStatusService }));
vi.mock('../config-service', () => ({
  configService: {
    read: vi.fn(() => ({
      plugin_config: {},
      server: { port: 8000, ssl: false },
      version: '0.1.0',
    })),
    serverDir: '/repo/apps/server',
  },
}));

import { frontendPluginNameForSession, sessionManager } from '../session-manager';

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  mocks.childProcesses.length = 0;
  mocks.spawn.mockImplementation(() => {
    const child = makeChild();
    mocks.childProcesses.push(child);
    return child;
  });
  for (const session of sessionManager.listSessions()) {
    sessionManager.removeSession(session.id);
  }
});

afterEach(() => {
  vi.useRealTimers();
});

describe('session-manager frontend plugin mapping', () => {
  it('uses provider-specific frontend plugins for session types', () => {
    expect(frontendPluginNameForSession('claude')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('claude-desktop')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('codex')).toBe('codex-frontend');
    expect(frontendPluginNameForSession('gemini')).toBe('gemini-frontend');
  });
});

describe('session-manager proxy startup', () => {
  it('kills and clears proxy state when readiness times out', async () => {
    const pending = sessionManager.createSession('claude', '/tmp/project');
    const rejected = expect(pending).rejects.toThrow('Proxy ready timeout');

    await vi.advanceTimersByTimeAsync(15_000);

    await rejected;
    expect(mocks.childProcesses[0].kill).toHaveBeenCalledWith('SIGTERM');
    const internal = sessionManager as unknown as {
      sessions: Map<string, { proxy: MockChild | null; proxyReady: unknown; status: string }>;
    };
    const session = internal.sessions.get('session-1');
    expect(session?.status).toBe('error');
    expect(session?.proxy).toBeNull();
    expect(session?.proxyReady).toBeNull();

    await vi.advanceTimersByTimeAsync(5_000);
    expect(mocks.childProcesses[0].kill).toHaveBeenCalledWith('SIGKILL');
  });

  it('can restart a session after proxy readiness timeout cleanup', async () => {
    const pending = sessionManager.createSession('claude', '/tmp/project');
    const rejected = expect(pending).rejects.toThrow('Proxy ready timeout');
    await vi.advanceTimersByTimeAsync(15_000);
    await rejected;

    const failedSession = sessionManager.listSessions()[0];
    const restarted = sessionManager.restartSession(failedSession.id);
    await vi.advanceTimersByTimeAsync(0);
    expect(mocks.childProcesses).toHaveLength(2);
    mocks.childProcesses[1].stdout.emit(
      'data',
      Buffer.from(
        JSON.stringify({
          event: 'ready',
          host: '127.0.0.1',
          pid: 123,
          port: 18000,
          scheme: 'http',
        }) + '\n',
      ),
    );

    await expect(restarted).resolves.toMatchObject({ id: failedSession.id, status: 'running' });
    expect(mocks.childProcesses[0].kill).toHaveBeenCalledWith('SIGTERM');
    expect(mocks.childProcesses[1].kill).not.toHaveBeenCalled();
  });
});
