// apps/desktop/src/renderer/src/lib/__tests__/benchmark-identity.test.ts
import { describe, it, expect } from 'vitest';
import {
  detectDatasetFilename,
  deriveBenchmarkId,
  deriveBenchmarkLabel,
  normalizeEvalContent,
  computeContentSignature,
  deriveBenchmarkIdentity,
  verifyIdentityConsistency,
} from '../benchmark-identity';
import type { EvalRunDetail, EvalQuestion } from '@/components/eval/types';

function q(idx: number, question: string, expected: string): EvalQuestion {
  return {
    id: `q-${idx}`,
    idx,
    question,
    expected,
    predicted: null,
    correct: null,
    raw_output: null,
    error: null,
  };
}

function makeRun(overrides: Partial<EvalRunDetail> = {}): EvalRunDetail {
  return {
    id: 'eval-run-1',
    spec_name: 'honest-agi-live-week-3',
    url4_expression:
      'https://screamingface.ai/honest-agi-live-week-3.eval.jsonl*(/claude($item.question))!reduce',
    started_at: '2026-05-04T11:00:00Z',
    finished_at: '2026-05-04T11:55:00Z',
    status: 'done',
    accuracy: 0.5,
    total_questions: 2,
    correct_questions: 1,
    error: null,
    favorite: false,
    questions: [q(0, '2+2?', '4'), q(1, 'capital of France?', 'Paris')],
    ...overrides,
  };
}

describe('detectDatasetFilename', () => {
  it('extracts the .eval.jsonl filename from a collection source URL', () => {
    expect(
      detectDatasetFilename(
        'https://screamingface.ai/honest-agi-live-week-3.eval.jsonl*(/claude($item.question))',
      ),
    ).toBe('honest-agi-live-week-3.eval.jsonl');
  });

  it('extracts a plain .jsonl filename', () => {
    expect(detectDatasetFilename('https://example.com/data.jsonl*(text)!intent')).toBe(
      'data.jsonl',
    );
  });

  it('prefers an .eval.jsonl over another dataset file in the same expression', () => {
    const expr = 'https://x.test/hle.eval.jsonl*(/python(reduce.csv)!{$item})';
    expect(detectDatasetFilename(expr)).toBe('hle.eval.jsonl');
  });

  it('returns null when there is no dataset filename', () => {
    expect(detectDatasetFilename('(/data/abc123)!$prompt')).toBeNull();
    expect(detectDatasetFilename('url4://ensemble(claude,codex)/hle')).toBeNull();
    expect(detectDatasetFilename('')).toBeNull();
  });
});

describe('deriveBenchmarkId', () => {
  it('strips the eval extension and slugifies', () => {
    expect(deriveBenchmarkId('honest-agi-live-week-3.eval.jsonl')).toBe('honest-agi-live-week-3');
  });

  it('slugifies spaces and underscores', () => {
    expect(deriveBenchmarkId('Honest AGI_Live week 3.jsonl')).toBe('honest-agi-live-week-3');
  });

  it('handles plain .json and .csv', () => {
    expect(deriveBenchmarkId('hle.json')).toBe('hle');
    expect(deriveBenchmarkId('data.csv')).toBe('data');
  });
});

describe('deriveBenchmarkLabel', () => {
  it('renders the Honest AGI Live week family', () => {
    expect(deriveBenchmarkLabel('honest-agi-live-week-3')).toBe('Honest AGI Live week 3');
    expect(deriveBenchmarkLabel('honest-agi-live')).toBe('Honest AGI Live');
  });

  it('uppercases known acronyms and titleizes the rest', () => {
    expect(deriveBenchmarkLabel('hle')).toBe('HLE');
    expect(deriveBenchmarkLabel('my-custom-bench')).toBe('My Custom Bench');
  });
});

describe('normalizeEvalContent', () => {
  it('orders rows by idx and emits {question, expected} jsonl', () => {
    const run = makeRun({
      questions: [q(1, 'capital of France?', 'Paris'), q(0, '2+2?', '4')],
    });
    expect(normalizeEvalContent(run)).toBe(
      '{"question":"2+2?","expected":"4"}\n{"question":"capital of France?","expected":"Paris"}',
    );
  });

  it('is empty for a run with no questions', () => {
    expect(normalizeEvalContent(makeRun({ questions: [] }))).toBe('');
  });
});

describe('computeContentSignature', () => {
  it('is a stable 64-char hex SHA-256 over the normalized content', async () => {
    const sig = await computeContentSignature(makeRun());
    expect(sig).toMatch(/^[0-9a-f]{64}$/);
    // Stable: same content -> same hash regardless of input row order.
    const reordered = await computeContentSignature(
      makeRun({ questions: [q(1, 'capital of France?', 'Paris'), q(0, '2+2?', '4')] }),
    );
    expect(reordered).toBe(sig);
  });

  it('differs when the eval content differs', async () => {
    const a = await computeContentSignature(makeRun());
    const b = await computeContentSignature(makeRun({ questions: [q(0, '2+2?', '5')] }));
    expect(b).not.toBe(a);
  });

  it('returns empty string for a run with no graded content', async () => {
    expect(await computeContentSignature(makeRun({ questions: [] }))).toBe('');
  });
});

describe('deriveBenchmarkIdentity', () => {
  it('derives id, label, filename, and signature from a collection run', async () => {
    const identity = await deriveBenchmarkIdentity(makeRun());
    expect(identity.datasetFilename).toBe('honest-agi-live-week-3.eval.jsonl');
    expect(identity.id).toBe('honest-agi-live-week-3');
    expect(identity.label).toBe('Honest AGI Live week 3');
    expect(identity.signature).toMatch(/^[0-9a-f]{64}$/);
  });

  it('falls back to spec_name when the expression has no dataset filename', async () => {
    const identity = await deriveBenchmarkIdentity(
      makeRun({ url4_expression: '(/data/abc)!$prompt', spec_name: 'hle' }),
    );
    expect(identity.datasetFilename).toBeNull();
    expect(identity.id).toBe('hle');
    expect(identity.label).toBe('HLE');
  });
});

describe('verifyIdentityConsistency', () => {
  it('passes a fully derived identity', () => {
    expect(
      verifyIdentityConsistency({
        id: 'honest-agi-live-week-3',
        label: 'Honest AGI Live week 3',
        datasetFilename: 'honest-agi-live-week-3.eval.jsonl',
        signature: 'a'.repeat(64),
      }),
    ).toEqual({ ok: true, reason: null });
  });

  it('blocks when the id could not be derived', () => {
    const out = verifyIdentityConsistency({
      id: '',
      label: '',
      datasetFilename: null,
      signature: 'a'.repeat(64),
    });
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/could not derive a benchmark id/i);
  });

  it('blocks when the signature is missing (no content to pin the id to)', () => {
    const out = verifyIdentityConsistency({
      id: 'hle',
      label: 'HLE',
      datasetFilename: 'hle.eval.jsonl',
      signature: '',
    });
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/no graded content/i);
  });
});
