// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunsList: () => ({ data: [], loading: false, error: null }),
}));
vi.mock('@/components/eval/EvalRunDetail', () => ({ EvalRunDetail: () => null }));

afterEach(cleanup);

import { EvalStudioView } from './EvalStudioView';

it('renders header, empty state, and both pane toggles', () => {
  render(<EvalStudioView />);
  expect(screen.getByText('Eval Studio')).toBeTruthy();
  expect(screen.getByText('Select a run to see details')).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide runs list/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide run details/i })).toBeTruthy();
});
