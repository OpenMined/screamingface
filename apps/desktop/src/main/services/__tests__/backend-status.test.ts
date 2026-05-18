import { describe, expect, it } from 'vitest';

import { escapeAppleScriptString } from '../backend-status';

describe('backend status service', () => {
  it('escapes cli commands before AppleScript interpolation', () => {
    expect(escapeAppleScriptString('say "hi" && printf \\ok')).toBe(
      'say \\"hi\\" && printf \\\\ok',
    );
    expect(escapeAppleScriptString('first\nsecond\rthird')).toBe('first\\nsecond\\rthird');
  });
});
