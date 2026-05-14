import { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  userData: '',
  appPath: '',
  resourcesPath: '',
}));

vi.mock('electron', () => ({
  app: {
    getPath: (name: string) => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`);
      return state.userData;
    },
    getAppPath: () => state.appPath,
  },
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }));

afterEach(() => {
  vi.resetModules();
  vi.restoreAllMocks();
});

describe('ConfigService packaged Codex migration', () => {
  it('copies sf.json to userData and activates gateway-backed Codex', async () => {
    state.userData = mkdtempSync(join(tmpdir(), 'sf-desktop-userdata-'));
    state.appPath = mkdtempSync(join(tmpdir(), 'sf-desktop-app-'));
    state.resourcesPath = mkdtempSync(join(tmpdir(), 'sf-desktop-resources-'));
    Object.defineProperty(process, 'resourcesPath', {
      configurable: true,
      value: state.resourcesPath,
    });

    const bundledServer = join(state.resourcesPath, 'server');
    mkdirSync(bundledServer, { recursive: true });
    writeFileSync(
      join(bundledServer, 'sf.json'),
      JSON.stringify({
        version: '0.1.0',
        server: { host: '0.0.0.0', port: 8000, reload: false, ssl: true },
        plugins: ['tracing', 'codex-backend-api'],
        plugin_config: {
          tracing: { phoenix_launch: false },
          'aigw-runner': { startup_timeout_seconds: 10 },
        },
      }),
    );

    const { configService } = await import('../config-service');

    const migrated = JSON.parse(readFileSync(configService.getConfigPath(), 'utf-8'));
    expect(migrated.plugins).toEqual(['tracing', 'aigw-runner', 'aigw-base', 'aigw-codex-backend']);
    expect(migrated.plugins).not.toContain('codex-backend-api');
    expect(migrated.plugin_config.tracing).toEqual({ phoenix_launch: false });
    expect(migrated.plugin_config['aigw-runner']).toEqual({
      startup_timeout_seconds: 60,
      aigateway_dir: join(state.userData, 'aigateway'),
      database_path: join(state.userData, 'aigateway', 'aigateway.db'),
      auth_enabled: false,
    });
  });

  it('creates userData before copying bundled config on first launch', async () => {
    const home = mkdtempSync(join(tmpdir(), 'sf-desktop-home-'));
    state.userData = join(home, 'Library', 'Application Support', 'ScreamingFace');
    state.appPath = mkdtempSync(join(tmpdir(), 'sf-desktop-app-'));
    state.resourcesPath = mkdtempSync(join(tmpdir(), 'sf-desktop-resources-'));
    Object.defineProperty(process, 'resourcesPath', {
      configurable: true,
      value: state.resourcesPath,
    });

    const bundledServer = join(state.resourcesPath, 'server');
    mkdirSync(bundledServer, { recursive: true });
    writeFileSync(
      join(bundledServer, 'sf.json'),
      JSON.stringify({
        version: '0.1.0',
        server: { host: '0.0.0.0', port: 8000, reload: false, ssl: true },
        plugins: ['codex-backend-api'],
        plugin_config: {},
      }),
    );

    const { configService } = await import('../config-service');

    expect(existsSync(state.userData)).toBe(true);
    expect(existsSync(configService.getConfigPath())).toBe(true);
  });
});
