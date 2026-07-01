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
});
