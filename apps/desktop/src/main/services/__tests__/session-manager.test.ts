import { describe, expect, it, vi } from 'vitest';

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => '/tmp/sf-user-data'),
    getAppPath: vi.fn(() => '/repo/apps/desktop'),
  },
  dialog: {},
  BrowserWindow: {},
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));

import { frontendPluginNameForSession } from '../session-manager';

describe('session-manager frontend plugin mapping', () => {
  it('uses provider-specific frontend plugins for session types', () => {
    expect(frontendPluginNameForSession('claude')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('claude-desktop')).toBe('claude-frontend');
    expect(frontendPluginNameForSession('codex')).toBe('codex-frontend');
    expect(frontendPluginNameForSession('gemini')).toBe('gemini-frontend');
  });
});
