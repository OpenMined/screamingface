import type { IpcMainInvokeEvent } from 'electron';
import { is } from '@electron-toolkit/utils';
import { join } from 'path';
import { pathToFileURL } from 'url';

export function requireTrustedIpcSender(event: IpcMainInvokeEvent): void {
  const frameUrl = event.senderFrame?.url ?? event.sender.getURL();
  if (!isTrustedIpcSenderUrl(frameUrl)) {
    throw new Error('untrusted IPC sender');
  }
}

export function isTrustedIpcSenderUrl(frameUrl: string, trustedRendererUrl?: string): boolean {
  let url: URL;
  try {
    url = new URL(frameUrl);
  } catch {
    return false;
  }

  if (url.protocol === 'file:') {
    const trusted = new URL(trustedRendererUrl ?? packagedRendererFileUrl());
    return (
      trusted.protocol === 'file:' &&
      url.pathname === trusted.pathname &&
      url.search === '' &&
      url.username === '' &&
      url.password === ''
    );
  }

  if (is.dev) {
    const rendererUrl = process.env['ELECTRON_RENDERER_URL'];
    if (rendererUrl) return sameOrigin(url, rendererUrl);
    return url.protocol === 'http:' && isLoopbackHostname(url.hostname);
  }

  return false;
}

function packagedRendererFileUrl(): string {
  return pathToFileURL(join(__dirname, '../renderer/index.html')).href;
}

function sameOrigin(url: URL, expectedUrlString: string): boolean {
  try {
    const expected = new URL(expectedUrlString);
    return url.origin === expected.origin;
  } catch {
    return false;
  }
}

function isLoopbackHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}
