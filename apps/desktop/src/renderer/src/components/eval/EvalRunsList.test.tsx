// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';
import type { EvalRunSummary } from './types';

const rows: EvalRunSummary[] = [
  {
    id: 'r1',
    spec_name: 'HLE',
    url4_expression: 'transform(url, intent)',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    status: 'done',
    accuracy: 0.9,
    total_questions: 10,
    correct_questions: 9,
    error: null,
  },
];

vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunsList: () => ({ data: rows, loading: false, error: null }),
}));

afterEach(cleanup);

import { EvalRunsList } from './EvalRunsList';

it('calls onRunLocally with the row spec + expression', () => {
  const onRunLocally = vi.fn();
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={onRunLocally} />);
  fireEvent.click(screen.getByRole('button', { name: /run locally/i }));
  expect(onRunLocally).toHaveBeenCalledWith({ spec: 'HLE', expression: 'transform(url, intent)' });
});
