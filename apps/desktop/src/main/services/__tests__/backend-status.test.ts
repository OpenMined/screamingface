import { createServer } from 'http';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AddressInfo } from 'net';

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

import {
  backendStatusService,
  escapeAppleScriptString,
  isStatusV2,
  parseBackendStatus,
  type BackendPollingError,
} from '../backend-status';

afterEach(() => {
  backendStatusService.stop();
});

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

  it('surfaces unsupported newer status envelopes as gateway misconfigured', () => {
    const status = parseBackendStatus({
      version: 3,
      gateway: {
        mode: 'external',
        managed_by_runner: false,
        reachable: true,
        authenticated: true,
        auth_required: true,
        url: 'https://gateway.example.com',
      },
    });

    expect(isStatusV2(status)).toBe(true);
    if (isStatusV2(status)) {
      expect(status.action).toBe('gateway_misconfigured');
      expect(status.message).toBe(
        'Desktop app is out of date — update required to use this SF server',
      );
      expect(status.gateway.url).toBe('https://gateway.example.com');
    }
  });

  it('emits polling errors with HTTP status and code', async () => {
    const server = createServer((_req, res) => {
      res.writeHead(401, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          detail: { code: 'desktop_secret_invalid', message: 'Desktop secret invalid' },
        }),
      );
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address() as AddressInfo;

    try {
      const errorPromise = new Promise<BackendPollingError>((resolve) => {
        backendStatusService.once('pollingError', (error) => resolve(error as BackendPollingError));
      });

      backendStatusService.start(`http://127.0.0.1:${address.port}`);

      await expect(errorPromise).resolves.toMatchObject({
        status: 401,
        code: 'desktop_secret_invalid',
        message: 'Desktop secret invalid',
        consecutiveFailures: 1,
      });
      expect(backendStatusService.getPollingError()).toMatchObject({
        status: 401,
        code: 'desktop_secret_invalid',
      });
    } finally {
      backendStatusService.stop();
      await new Promise<void>((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()));
      });
    }
  });
});
