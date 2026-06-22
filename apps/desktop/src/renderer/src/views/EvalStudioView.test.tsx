// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

const runsData = { data: [] as unknown[], loading: false, error: null, refresh: vi.fn() };
vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunsList: () => runsData,
}));
vi.mock('@/hooks/use-eval-run-actions', () => ({
  useEvalRunActions: () => ({ toggleFavorite: vi.fn(), deleteRun: vi.fn() }),
}));
vi.mock('@/hooks/use-start-eval-run', () => ({ useStartEvalRun: () => () => null }));
vi.mock('@/hooks/use-backend-status', () => ({
  useBackendStatus: () => ({
    statuses: {},
    pollingError: null,
    loaded: true,
    refresh: vi.fn().mockResolvedValue({}),
  }),
  isBackendStatusV2: () => false,
}));
vi.mock('@/components/eval/EvalRunDetail', () => ({ EvalRunDetail: () => null }));
vi.mock('@/hooks/use-publish-logs', () => ({
  usePublishLogs: () => ({ logs: [], clearLogs: vi.fn() }),
}));

afterEach(cleanup);

import { EvalStudioView } from './EvalStudioView';

afterEach(() => {
  runsData.data = [];
});

it('renders header, empty state, and both pane toggles', () => {
  render(<EvalStudioView />);
  expect(screen.getByText('Eval Studio')).toBeTruthy();
  expect(screen.getByText('Select a run to see details')).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide runs list/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide run details/i })).toBeTruthy();
});

// SF-289: the resizable Panel hard-codes inline overflow:hidden, so the runs
// list must live inside its own bounded, scrollable container or it gets clipped.
it('wraps the runs list in a bounded scroll container', () => {
  runsData.data = Array.from({ length: 30 }, (_, i) => ({
    id: `run-${i}`,
    spec_name: `Spec ${i}`,
    started_at: '2026-06-20T00:00:00Z',
    status: 'done',
    favorite: false,
    url4_expression: 'x',
  }));
  render(<EvalStudioView />);
  const firstRun = screen.getByText('Spec 0');
  expect(firstRun.closest('.overflow-y-auto.h-full')).not.toBeNull();
});
