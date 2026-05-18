import { existsSync, mkdtempSync, readdirSync, readFileSync } from 'fs';
import { tmpdir } from 'os';
import { join, resolve } from 'path';
import { describe, expect, it, vi } from 'vitest';

const electronMocks = vi.hoisted(() => ({
  app: {
    getAppPath: vi.fn(() => '/repo/apps/desktop'),
    getPath: vi.fn(() => '/tmp/sf-user-data'),
  },
}));

vi.mock('electron', () => ({ app: electronMocks.app }));
vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));

import { ConfigService } from '../config-service';

describe('ConfigService', () => {
  it('defers Electron path resolution until first use', () => {
    new ConfigService();

    expect(electronMocks.app.getAppPath).not.toHaveBeenCalled();
    expect(electronMocks.app.getPath).not.toHaveBeenCalled();
  });

  it('writes config through a same-directory temp file and rename', () => {
    const dir = mkdtempSync(join(tmpdir(), 'sf-config-'));
    const configPath = join(dir, 'sf.json');
    const service = new ConfigService();

    service.setConfigPath(configPath);
    service.write({ version: '0.1.0', plugins: [] });

    expect(readFileSync(configPath, 'utf-8')).toBe(
      JSON.stringify({ version: '0.1.0', plugins: [] }, null, 2) + '\n',
    );
    expect(readdirSync(dir).filter((name) => name.endsWith('.tmp'))).toEqual([]);
    expect(existsSync(resolve(dir, 'sf.json'))).toBe(true);
  });
});
