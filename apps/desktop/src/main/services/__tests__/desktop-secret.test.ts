import { mkdtempSync, rmSync, statSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { describe, expect, it, vi } from 'vitest';

const electronMocks = vi.hoisted(() => ({
  app: {
    getPath: vi.fn(),
  },
}));

vi.mock('electron', () => ({ app: electronMocks.app }));

import {
  desktopSecretHeader,
  getDesktopSecretPath,
  getDesktopSecretValue,
} from '../desktop-secret';

describe('desktop secret', () => {
  it('creates a 0600 shared secret and reuses it for headers', () => {
    const userData = mkdtempSync(join(tmpdir(), 'sf-desktop-secret-'));
    electronMocks.app.getPath.mockReturnValue(userData);

    try {
      const path = join(userData, '.sf', 'runtime', 'desktop.secret');
      const secret = getDesktopSecretValue();

      expect(getDesktopSecretPath()).toBe(path);
      expect(secret).toMatch(/^[A-Za-z0-9_-]+$/);
      expect(statSync(path).mode & 0o777).toBe(0o600);
      expect(getDesktopSecretValue()).toBe(secret);
      expect(desktopSecretHeader()).toEqual({ 'X-SF-Desktop-Secret': secret });
    } finally {
      rmSync(userData, { recursive: true, force: true });
    }
  });
});
