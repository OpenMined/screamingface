import type { WebFrameMain } from 'electron';

function rendererDevOrigin(): string | null {
  const value = process.env.ELECTRON_RENDERER_URL;
  if (!value) return null;
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

export function isValidSender(frame: WebFrameMain | null): boolean {
  if (!frame?.url) return false;
  try {
    const parsed = new URL(frame.url);
    const devOrigin = rendererDevOrigin();
    if (devOrigin) return parsed.origin === devOrigin;
    return parsed.protocol === 'file:' && parsed.pathname.endsWith('/renderer/index.html');
  } catch {
    return false;
  }
}

export function assertValidSender(frame: WebFrameMain | null): void {
  if (!isValidSender(frame)) {
    throw new Error('invalid IPC sender');
  }
}
