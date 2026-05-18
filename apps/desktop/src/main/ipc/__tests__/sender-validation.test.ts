import { describe, expect, it, vi } from 'vitest';

const { is } = vi.hoisted(() => ({ is: { dev: true } }));

vi.mock('@electron-toolkit/utils', () => ({ is }));

import { isTrustedIpcSenderUrl } from '../sender-validation';

describe('IPC sender validation', () => {
  it('trusts packaged file renderer URLs', () => {
    is.dev = false;
    const trustedRendererUrl = 'file:///Applications/ScreamingFace.app/out/renderer/index.html';

    expect(isTrustedIpcSenderUrl(trustedRendererUrl, trustedRendererUrl)).toBe(true);
    expect(
      isTrustedIpcSenderUrl(
        'file:///Applications/ScreamingFace.app/Contents/Resources/evil.html',
        trustedRendererUrl,
      ),
    ).toBe(false);
    expect(isTrustedIpcSenderUrl('https://example.com')).toBe(false);
  });

  it('trusts only loopback HTTP origins in dev', () => {
    is.dev = true;
    delete process.env['ELECTRON_RENDERER_URL'];

    expect(isTrustedIpcSenderUrl('http://localhost:5173')).toBe(true);
    expect(isTrustedIpcSenderUrl('http://127.0.0.1:5173')).toBe(true);
    expect(isTrustedIpcSenderUrl('http://192.168.1.5:5173')).toBe(false);
    expect(isTrustedIpcSenderUrl('https://example.com')).toBe(false);
  });

  it('honors an explicit dev renderer origin', () => {
    is.dev = true;
    process.env['ELECTRON_RENDERER_URL'] = 'http://127.0.0.1:5173';

    expect(isTrustedIpcSenderUrl('http://127.0.0.1:5173/settings')).toBe(true);
    expect(isTrustedIpcSenderUrl('http://127.0.0.1:5174/settings')).toBe(false);

    delete process.env['ELECTRON_RENDERER_URL'];
  });
});
