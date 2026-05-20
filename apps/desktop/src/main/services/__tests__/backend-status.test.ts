import { describe, expect, it, vi } from 'vitest';

vi.mock('electron', () => ({
  Notification: class {
    static isSupported(): boolean {
      return false;
    }
    show(): void {
      /* noop */
    }
  },
  app: {
    getPath: () => '/tmp/sf-test-user-data',
    getAppPath: () => '/tmp/sf-test-app',
  },
}));

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));

import { escapeAppleScriptString, isStatusV2, parseBackendStatus } from '../backend-status';

describe('backend status service', () => {
  it('escapes cli commands before AppleScript interpolation', () => {
    expect(escapeAppleScriptString('say "hi" && printf \\ok')).toBe(
      'say \\"hi\\" && printf \\\\ok',
    );
    expect(escapeAppleScriptString('first\nsecond\rthird')).toBe('first\\nsecond\\rthird');
  });

  it('keeps legacy status maps for local-managed compatibility', () => {
    const status = parseBackendStatus({ claude: { authenticated: true, action: 'healthy' } });

    expect(isStatusV2(status)).toBe(false);
    expect(status).toEqual({ claude: { authenticated: true, action: 'healthy' } });
  });

  it('fails closed when desktop is external but SF only returns v1 status', () => {
    const status = parseBackendStatus(
      { claude: { authenticated: true, action: 'healthy' } },
      { mode: 'external', gateway_url: 'https://gateway.example.com' },
    );

    expect(isStatusV2(status)).toBe(true);
    if (isStatusV2(status)) {
      expect(status.action).toBe('gateway_misconfigured');
      expect(status.message).toBe(
        'SF server is out of date — update required to use external gateway mode',
      );
      expect(status.gateway.url).toBe('https://gateway.example.com');
    }
  });

  it('does not classify malformed v2 without gateway as v2 status', () => {
    const malformed = { version: 2 };

    expect(isStatusV2(malformed)).toBe(false);
    expect(() => parseBackendStatus(malformed)).toThrow('Unsupported /backends/status response');
  });
});
