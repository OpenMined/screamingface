import { EventEmitter } from 'events';
import { mkdtempSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  userData: '',
  spawn: vi.fn(),
  execFileSync: vi.fn(() => Buffer.from('{}')),
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }));

vi.mock('electron', () => ({
  app: {
    getPath: (name: string) => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`);
      return state.userData;
    },
  },
}));

vi.mock('child_process', () => ({
  spawn: state.spawn,
  execFileSync: state.execFileSync,
  execFile: vi.fn(),
}));

vi.mock('../config-service', () => ({
  configService: {
    serverDir: '/unused/dev/server',
    read: () => ({ plugins: ['aigw-runner', 'aigw-base', 'aigw-codex-backend'] }),
  },
}));

vi.mock('../uv-resolver', () => ({
  resolveUv: () => '/Applications/ScreamingFace.app/Contents/Resources/server/bin/uv',
}));

function fakeChild(): EventEmitter & {
  stdout: EventEmitter;
  stderr: EventEmitter;
  kill: ReturnType<typeof vi.fn>;
} {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
    kill: ReturnType<typeof vi.fn>;
  };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = vi.fn();
  return child;
}

afterEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('ServerProcess packaged startup', () => {
  it('spawns SF from userData with loopback bind and explicit gateway runner env', async () => {
    state.userData = mkdtempSync(join(tmpdir(), 'sf-desktop-userdata-'));
    state.spawn.mockReturnValue(fakeChild());

    const { serverProcess } = await import('../server-process');

    await expect(serverProcess.start()).resolves.toBe(true);
    const [cmd, args, opts] = state.spawn.mock.calls[0];
    expect(cmd).toBe(join(state.userData, '.venv', 'bin', 'sf'));
    expect(args).toEqual([
      'run',
      '--subprocess',
      '--config-json',
      JSON.stringify({ plugins: ['aigw-runner', 'aigw-base', 'aigw-codex-backend'] }),
      '--host',
      '127.0.0.1',
    ]);
    expect(opts.cwd).toBe(state.userData);
    expect(opts.env.SF_AIGW_RUNNER__AIGATEWAY_DIR).toBe(join(state.userData, 'aigateway'));
    expect(opts.env.SF_AIGW_RUNNER__DATABASE_PATH).toBe(
      join(state.userData, 'aigateway', 'aigateway.db'),
    );
    expect(opts.env.SF_AIGW_RUNNER__AUTH_ENABLED).toBe('false');
    expect(opts.env.SF_AIGW_RUNNER__UV_BIN).toBe(
      '/Applications/ScreamingFace.app/Contents/Resources/server/bin/uv',
    );
    expect(opts.env.SF_AIGW_RUNNER__AIGATEWAY_DIR).not.toContain('..');
  });
});
