import { mkdtempSync, mkdirSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }));

afterEach(() => {
  vi.resetModules();
});

describe('resolveUv packaged mode', () => {
  it('prefers bundled uv from extraResources', async () => {
    const resourcesPath = mkdtempSync(join(tmpdir(), 'sf-desktop-resources-'));
    const bundledUv = join(resourcesPath, 'server', 'bin', 'uv');
    mkdirSync(join(resourcesPath, 'server', 'bin'), { recursive: true });
    writeFileSync(bundledUv, 'uv');
    Object.defineProperty(process, 'resourcesPath', {
      configurable: true,
      value: resourcesPath,
    });

    const { resolveUv } = await import('../uv-resolver');

    expect(resolveUv()).toBe(bundledUv);
  });
});
