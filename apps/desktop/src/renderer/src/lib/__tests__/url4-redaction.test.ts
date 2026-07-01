// apps/desktop/src/renderer/src/lib/__tests__/url4-redaction.test.ts
import { describe, it, expect } from 'vitest';
import {
  findLocalDataRefs,
  hasLocalDataRefs,
  sanitizeDataRefs,
  parseSpecName,
  deriveProviders,
} from '../url4-redaction';

describe('findLocalDataRefs / hasLocalDataRefs', () => {
  it('returns [] for an expression with no /data refs', () => {
    const expr = 'url4://ensemble(claude,codex)/hle';
    expect(findLocalDataRefs(expr)).toEqual([]);
    expect(hasLocalDataRefs(expr)).toBe(false);
  });

  it('finds a single /data blob ref', () => {
    const expr = '(/data/a1b2c3d4e5f6)!$prompt';
    expect(findLocalDataRefs(expr)).toEqual(['/data/a1b2c3d4e5f6']);
    expect(hasLocalDataRefs(expr)).toBe(true);
  });

  it('finds multiple /data refs including nested paths', () => {
    const expr = '/python(/data/code/check.py)!{/data/abc123}';
    expect(findLocalDataRefs(expr)).toEqual(['/data/code/check.py', '/data/abc123']);
    expect(hasLocalDataRefs(expr)).toBe(true);
  });

  it('handles empty input', () => {
    expect(findLocalDataRefs('')).toEqual([]);
    expect(hasLocalDataRefs('')).toBe(false);
  });
});

describe('sanitizeDataRefs', () => {
  it('replaces every /data ref with /data/<redacted>', () => {
    const expr = '/python(/data/code/check.py)!{/data/abc123}';
    expect(sanitizeDataRefs(expr)).toBe('/python(/data/<redacted>)!{/data/<redacted>}');
  });

  it('leaves expressions without /data refs unchanged', () => {
    const expr = 'url4://ensemble(claude,codex,gemini)/hle';
    expect(sanitizeDataRefs(expr)).toBe(expr);
  });

  it('handles empty input', () => {
    expect(sanitizeDataRefs('')).toBe('');
  });
});

describe('parseSpecName', () => {
  it('splits on the first colon into benchmark/spec', () => {
    expect(parseSpecName('hle:hle-ensemble-three')).toEqual({
      benchmark_id: 'hle',
      spec_id: 'hle-ensemble-three',
    });
  });

  it('splits only on the first colon', () => {
    expect(parseSpecName('hle:spec:with:colons')).toEqual({
      benchmark_id: 'hle',
      spec_id: 'spec:with:colons',
    });
  });

  it('returns null benchmark and full name as spec when there is no colon', () => {
    expect(parseSpecName('hle-claude-single')).toEqual({
      benchmark_id: null,
      spec_id: 'hle-claude-single',
    });
  });

  it('treats an empty benchmark segment as null', () => {
    expect(parseSpecName(':spec-only')).toEqual({ benchmark_id: null, spec_id: 'spec-only' });
  });
});

describe('deriveProviders', () => {
  it('extracts providers from an ensemble expression in stable order', () => {
    expect(deriveProviders('url4://ensemble(claude,codex,gemini)/hle')).toEqual([
      'claude',
      'codex',
      'gemini',
    ]);
  });

  it('is order-stable regardless of expression order', () => {
    expect(deriveProviders('gemini,claude')).toEqual(['claude', 'gemini']);
  });

  it('returns [] when no known provider token is present', () => {
    expect(deriveProviders('url4://benchmark/spec')).toEqual([]);
    expect(deriveProviders('')).toEqual([]);
  });

  it('detects ollama', () => {
    expect(deriveProviders('(ollama)!$prompt')).toEqual(['ollama']);
  });

  it('detects antigravity', () => {
    expect(deriveProviders('/antigravity($prompt)!answer')).toEqual(['antigravity']);
  });

  it('detects huggingface', () => {
    expect(deriveProviders('/huggingface($prompt)!answer')).toEqual(['huggingface']);
  });
});
