import { describe, it, expect } from 'vitest';
import { clampEditorHeight } from '../editor-height';

describe('clampEditorHeight', () => {
  it('floors at 28px', () => {
    expect(clampEditorHeight(10, 360)).toBe(28);
  });
  it('caps at the given maximum', () => {
    expect(clampEditorHeight(500, 360)).toBe(360);
  });
  it('returns content height between the floor and the cap', () => {
    expect(clampEditorHeight(120, 360)).toBe(120);
  });
  it('removes the cap when max is null (full content height)', () => {
    expect(clampEditorHeight(5000, null)).toBe(5000);
    expect(clampEditorHeight(10, null)).toBe(28);
  });
});
