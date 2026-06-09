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

it('renders compact rows (not a table) with spec name, date, status, accuracy', () => {
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={vi.fn()} />);
  expect(screen.queryByRole('table')).toBeNull();
  expect(screen.getByText('HLE')).toBeTruthy();
  expect(screen.getByText(/done/i)).toBeTruthy();
  expect(screen.getByText('90.0%')).toBeTruthy();
});

it('selects the run when the row is clicked', () => {
  const onSelect = vi.fn();
  render(<EvalRunsList selectedId={null} onSelect={onSelect} onRunLocally={vi.fn()} />);
  fireEvent.click(screen.getByText('HLE'));
  expect(onSelect).toHaveBeenCalledWith('r1');
});
