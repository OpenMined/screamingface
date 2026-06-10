// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';
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
    favorite: false,
  },
  {
    id: 'r2',
    spec_name: 'GPQA',
    url4_expression: 'x',
    started_at: '2026-01-02T00:00:00Z',
    finished_at: null,
    status: 'running',
    accuracy: null,
    total_questions: null,
    correct_questions: null,
    error: null,
    favorite: true,
  },
];

const { refresh, toggleFavorite } = vi.hoisted(() => ({
  refresh: vi.fn(),
  toggleFavorite: vi.fn().mockResolvedValue(true),
}));

vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunsList: () => ({ data: rows, loading: false, error: null, refresh }),
}));
vi.mock('@/hooks/use-eval-run-actions', () => ({
  useEvalRunActions: () => ({ toggleFavorite }),
}));

beforeEach(() => {
  refresh.mockClear();
  toggleFavorite.mockClear();
});
afterEach(cleanup);

import { EvalRunsList } from './EvalRunsList';

it('calls onRunLocally with the row spec + expression', () => {
  const onRunLocally = vi.fn();
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={onRunLocally} />);
  fireEvent.click(screen.getAllByRole('button', { name: /run locally/i })[0]);
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

it('reflects favorite state via the star control', () => {
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={vi.fn()} />);
  // r1 is not favorited (label "Favorite"), r2 is (label "Unfavorite").
  expect(screen.getByRole('button', { name: 'Favorite' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Unfavorite' })).toBeTruthy();
});

it('toggles favorite on the un-favorited row', async () => {
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Favorite' }));
  await waitFor(() => expect(toggleFavorite).toHaveBeenCalledWith('r1', true));
  expect(refresh).toHaveBeenCalled();
});

it('has no delete control in the list (delete lives in the detail panel)', () => {
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={vi.fn()} />);
  expect(screen.queryByRole('button', { name: /delete run/i })).toBeNull();
});
