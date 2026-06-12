// apps/desktop/src/renderer/src/components/eval/types.ts
//
// Mirrors apps/server/src/screamingface/plugins/eval_runs/schemas.py.
// If the server schema changes, update both.

export type EvalRunStatus = 'running' | 'done' | 'failed' | 'degraded';

export interface EvalRunSummary {
  id: string;
  spec_name: string;
  url4_expression: string;
  started_at: string; // ISO 8601
  finished_at: string | null;
  status: EvalRunStatus;
  accuracy: number | null; // 0..1
  total_questions: number | null;
  correct_questions: number | null;
  error: string | null;
  favorite: boolean;
}

export interface EvalQuestion {
  id: string;
  idx: number;
  question: string;
  expected: string;
  predicted: string | null;
  correct: boolean | null;
  raw_output: string | null;
  error: string | null;
}

export interface EvalRunDetail extends EvalRunSummary {
  questions: EvalQuestion[];
}
