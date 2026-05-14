import type { WebFrameMain } from 'electron';
import { afterEach, describe, expect, it } from 'vitest';

import { isValidSender } from '../validate-sender';

function frame(url: string): WebFrameMain {
  return { url } as WebFrameMain;
}

afterEach(() => {
  delete process.env.ELECTRON_RENDERER_URL;
});

describe('isValidSender', () => {
  it('allows the configured dev renderer origin', () => {
    process.env.ELECTRON_RENDERER_URL = 'http://localhost:5173/';

    expect(isValidSender(frame('http://localhost:5173/settings'))).toBe(true);
  });

  it('rejects other dev origins', () => {
    process.env.ELECTRON_RENDERER_URL = 'http://localhost:5173/';

    expect(isValidSender(frame('http://evil.example.com/'))).toBe(false);
  });

  it('allows the packaged renderer file', () => {
    expect(isValidSender(frame('file:///Applications/ScreamingFace.app/renderer/index.html'))).toBe(
      true,
    );
  });

  it('rejects unrelated file URLs', () => {
    expect(isValidSender(frame('file:///tmp/other.html'))).toBe(false);
  });
});
