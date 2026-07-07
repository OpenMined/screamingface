// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';

const knownBenchmarksState: {
  benchmarks: Array<{ id: string; displayName: string }> | null;
  loading: boolean;
} = { benchmarks: null, loading: true };

const leaderboardState: {
  data: { benchmark: unknown; entries: unknown[] } | null;
  loading: boolean;
  error: boolean;
  refresh: () => void;
} = { data: null, loading: false, error: false, refresh: vi.fn() };

vi.mock('@/hooks/use-known-benchmarks', () => ({
  useKnownBenchmarks: () => knownBenchmarksState,
}));
vi.mock('@/hooks/use-leaderboard', () => ({
  useLeaderboard: () => leaderboardState,
}));
vi.mock('@/components/leaderboard/LeaderboardTable', () => ({
  LeaderboardTable: ({ entries }: { entries: unknown[] }) => (
    <div data-testid="leaderboard-table">{entries.length} entries</div>
  ),
}));

afterEach(cleanup);

import { LeaderboardView } from './LeaderboardView';

beforeEach(() => {
  knownBenchmarksState.benchmarks = null;
  knownBenchmarksState.loading = true;
  leaderboardState.data = null;
  leaderboardState.loading = false;
  leaderboardState.error = false;
});

it('shows a loading state while benchmarks are loading', () => {
  render(<LeaderboardView />);
  expect(screen.getByText(/loading benchmarks/i)).toBeTruthy();
});

it('shows a distinct empty state when no benchmarks are registered', () => {
  knownBenchmarksState.benchmarks = [];
  knownBenchmarksState.loading = false;
  render(<LeaderboardView />);
  expect(screen.getByText(/no benchmarks are registered/i)).toBeTruthy();
});

it('renders the benchmark selector and table once benchmarks and leaderboard data load', () => {
  knownBenchmarksState.benchmarks = [{ id: 'livetruth', displayName: 'LiveTruth' }];
  knownBenchmarksState.loading = false;
  leaderboardState.data = { benchmark: { id: 'livetruth' }, entries: [1, 2] };
  render(<LeaderboardView />);
  expect(screen.getByLabelText('Benchmark')).toBeTruthy();
  expect(screen.getByTestId('leaderboard-table')).toHaveTextContent('2 entries');
});

it('shows the leaderboard loading state distinct from the benchmarks loading state', () => {
  knownBenchmarksState.benchmarks = [{ id: 'livetruth', displayName: 'LiveTruth' }];
  knownBenchmarksState.loading = false;
  leaderboardState.loading = true;
  render(<LeaderboardView />);
  expect(screen.getByText(/loading leaderboard/i)).toBeTruthy();
});

it('shows a retry button on error, distinct from the empty-entries state', () => {
  knownBenchmarksState.benchmarks = [{ id: 'livetruth', displayName: 'LiveTruth' }];
  knownBenchmarksState.loading = false;
  leaderboardState.error = true;
  render(<LeaderboardView />);
  expect(screen.getByText(/couldn't load the leaderboard/i)).toBeTruthy();
  expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
});
