import { describe, expect, it } from 'vitest';
import { referencedBackends } from '../referenced-backends';

describe('referencedBackends', () => {
  it('finds the single backend in ScoredLiveTruth (claude only)', () => {
    expect(referencedBackends("(...consensus=/claude($item.q)!'x'...)")).toEqual(['claude']);
  });
  it('finds all three in a 3-way ensemble', () => {
    const e = '(claude:/claude($q)!a, codex:/codex($q)!b, gemini:/gemini($q)!c)!reduce';
    expect(referencedBackends(e).sort()).toEqual(['claude', 'codex', 'gemini']);
  });
  it('finds antigravity backend references', () => {
    expect(referencedBackends('/antigravity($q)!answer')).toEqual(['antigravity']);
  });
  it('finds huggingface backend references', () => {
    expect(referencedBackends('/huggingface($q)!answer')).toEqual(['huggingface']);
  });
  it('excludes /python and /data (non-auth, not model backends)', () => {
    expect(referencedBackends('/python(/data/code/check_correct.py)!{}')).toEqual([]);
  });
  // SF-346: profile-alias form `/backend/<alias>` must still resolve to the
  // backend. The `/name\b` word boundary already matches (existing behavior;
  // locked here so a future regex change can't silently break alias detection).
  it('detects the backend from an alias-form path (/huggingface/oss20b)', () => {
    expect(referencedBackends('/huggingface/oss20b($q)!answer')).toEqual(['huggingface']);
  });
  it('detects each backend in an alias-form ensemble', () => {
    const e = '(a:/huggingface/oss20b($q)!x, b:/gemini/flash($q)!y)!reduce';
    expect(referencedBackends(e).sort()).toEqual(['gemini', 'huggingface']);
  });
  it('does not detect provider names inside alias segments', () => {
    expect(referencedBackends('/huggingface/claude-alt($q)!answer')).toEqual(['huggingface']);
    expect(referencedBackends('/ollama/codex-clone($q)!answer')).toEqual(['ollama']);
  });
});
