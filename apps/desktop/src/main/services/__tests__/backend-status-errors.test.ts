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

import { __testing } from '../backend-status';

describe('backend status error messages', () => {
  it('extracts nested FastAPI validation messages', () => {
    const body = JSON.stringify({
      detail: {
        detail: [
          {
            type: 'value_error',
            loc: ['body', 'password'],
            msg: 'Value error, password must be 8-72 UTF-8 bytes',
            input: 'short',
          },
        ],
      },
    });

    expect(__testing.extractErrorMessage(body)).toBe(
      'password: Value error, password must be 8-72 UTF-8 bytes',
    );
  });
});
