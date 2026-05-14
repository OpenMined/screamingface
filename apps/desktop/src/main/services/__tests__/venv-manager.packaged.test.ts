import { EventEmitter } from 'events';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  userData: '',
  resourcesPath: '',
  spawn: vi.fn(),
  execFileSync: vi.fn(() => 'Python 3.12.9\n'),
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }));

vi.mock('electron', () => ({
  app: {
    getPath: (name: string) => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`);
      return state.userData;
    },
    getVersion: () => '0.1.0-test',
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
  },
}));

vi.mock('../uv-resolver', () => ({
  resolveUv: () => join(state.resourcesPath, 'server', 'bin', 'uv'),
}));

function successfulChild(): EventEmitter & { stdout: EventEmitter; stderr: EventEmitter } {
  const child = new EventEmitter() as EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  process.nextTick(() => child.emit('close', 0));
  return child;
}

function writePackagedResources(resourcesPath: string): void {
  mkdirSync(join(resourcesPath, 'server', 'bin'), { recursive: true });
  mkdirSync(join(resourcesPath, 'server', 'python', 'bin'), { recursive: true });
  mkdirSync(join(resourcesPath, 'aigateway', 'src', 'aigateway'), { recursive: true });
  writeFileSync(join(resourcesPath, 'server', 'bin', 'uv'), 'uv');
  writeFileSync(join(resourcesPath, 'server', 'python', 'bin', 'python3.12'), 'python');
  writeFileSync(join(resourcesPath, 'server', 'pyproject.toml'), '[project]\nname="server"\n');
  writeFileSync(join(resourcesPath, 'server', 'uv.lock'), '# server lock\n');
  writeFileSync(
    join(resourcesPath, 'aigateway', 'pyproject.toml'),
    '[project]\nname="aigateway"\n',
  );
  writeFileSync(join(resourcesPath, 'aigateway', 'uv.lock'), '# gateway lock\n');
  writeFileSync(join(resourcesPath, 'aigateway', 'src', 'aigateway', '__init__.py'), '');
}

afterEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('VenvManager packaged gateway provisioning', () => {
  it('detects missing gateway venv as resync and copies gateway project during sync', async () => {
    state.userData = mkdtempSync(join(tmpdir(), 'sf-desktop-userdata-'));
    state.resourcesPath = mkdtempSync(join(tmpdir(), 'sf-desktop-resources-'));
    writePackagedResources(state.resourcesPath);
    mkdirSync(join(state.userData, '.venv', 'bin'), { recursive: true });
    writeFileSync(join(state.userData, '.venv', 'bin', 'python'), 'python');
    Object.defineProperty(process, 'resourcesPath', {
      configurable: true,
      value: state.resourcesPath,
    });
    state.spawn.mockImplementation(() => successfulChild());

    const { venvManager } = await import('../venv-manager');

    await expect(venvManager.detect()).resolves.toMatchObject({
      status: 'ready',
      uvFound: true,
      needsSync: true,
      autoBootstrap: false,
    });
    await expect(venvManager.sync()).resolves.toBe(true);

    const gatewayDir = join(state.userData, 'aigateway');
    expect(readFileSync(join(gatewayDir, 'pyproject.toml'), 'utf-8')).toContain('aigateway');
    expect(readFileSync(join(gatewayDir, 'uv.lock'), 'utf-8')).toContain('gateway lock');
    expect(existsSync(join(gatewayDir, 'src', 'aigateway', '__init__.py'))).toBe(true);
    expect(readFileSync(join(state.userData, '.sf-version'), 'utf-8')).toBe('0.1.0-test');

    const gatewaySync = state.spawn.mock.calls.find(
      ([, , opts]) =>
        opts?.cwd === gatewayDir && opts?.env?.VIRTUAL_ENV === join(gatewayDir, '.venv'),
    );
    expect(gatewaySync).toBeTruthy();
    expect(gatewaySync?.[1]).toEqual([
      'sync',
      '--python',
      join(state.resourcesPath, 'server', 'python', 'bin', 'python3.12'),
      '--no-install-project',
    ]);

    const serverSync = state.spawn.mock.calls.find(
      ([, args, opts]) => opts?.cwd === state.userData && args?.[0] === 'sync',
    );
    expect(serverSync?.[1]).toEqual([
      'sync',
      '--python',
      join(state.resourcesPath, 'server', 'python', 'bin', 'python3.12'),
      '--no-install-project',
    ]);
    expect(gatewayDir).not.toContain('..');
  });
});
