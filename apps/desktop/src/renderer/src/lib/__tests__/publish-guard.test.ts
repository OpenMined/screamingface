import { describe, it, expect } from 'vitest';
import { publishBlockReason } from '../publish-guard';
import type { EvalRunDetail } from '@/components/eval/types';

const RUN: EvalRunDetail = {
  id: 'r1',
  spec_name: 'hle:hle-ensemble-three',
  url4_expression: 'url4://ensemble(claude)/hle',
  started_at: '2026-05-04T11:00:00Z',
  finished_at: '2026-05-04T11:55:00Z',
  status: 'done',
  accuracy: 0.81,
  total_questions: 1000,
  correct_questions: 810,
  error: null,
  favorite: false,
  questions: [],
};

const EXPR = RUN.url4_expression;

describe('publishBlockReason', () => {
  it('passes a normal completed run', () => {
    expect(publishBlockReason({ run: RUN, url4Expression: EXPR })).toBeNull();
  });

  it('blocks a run with zero graded questions (degraded/empty)', () => {
    const reason = publishBlockReason({
      run: { ...RUN, total_questions: 0, correct_questions: 0 },
      url4Expression: EXPR,
    });
    expect(reason).toMatch(/no graded questions/i);
  });

  it('blocks a null total_questions', () => {
    const reason = publishBlockReason({
      run: { ...RUN, total_questions: null as unknown as number },
      url4Expression: EXPR,
    });
    expect(reason).toMatch(/no graded questions/i);
  });

  it('blocks inconsistent totals (correct > total)', () => {
    const reason = publishBlockReason({
      run: { ...RUN, total_questions: 2, correct_questions: 3 },
      url4Expression: EXPR,
    });
    expect(reason).toMatch(/inconsistent/i);
  });

  it('blocks an empty url4 expression to publish', () => {
    expect(publishBlockReason({ run: RUN, url4Expression: '   ' })).toMatch(/no URL4 expression/i);
  });
});
