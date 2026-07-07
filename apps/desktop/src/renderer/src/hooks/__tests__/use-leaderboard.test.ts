// @vitest-environment jsdom
import { renderHook, waitFor, cleanup, act } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';
import { useLeaderboard } from '../use-leaderboard';

const getLeaderboard = vi.fn();
const DATA = {
  benchmark: { id: 'livetruth', displayName: 'LiveTruth', description: null, datasetUrl: null },
  entries: [],
};

beforeEach(() => {
  getLeaderboard.mockReset();
  (window as unknown as { electronAPI: unknown }).electronAPI = { leaderboard: { getLeaderboard } };
});
afterEach(cleanup);

it('does nothing while benchmarkId is null', () => {
  const { result } = renderHook(() => useLeaderboard(null));
  expect(result.current.loading).toBe(false);
  expect(result.current.data).toBeNull();
  expect(getLeaderboard).not.toHaveBeenCalled();
});

it('loads, then resolves data for the given benchmark', async () => {
  getLeaderboard.mockResolvedValue(DATA);
  const { result } = renderHook(() => useLeaderboard('livetruth'));
  expect(result.current.loading).toBe(true);
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.data).toEqual(DATA);
  expect(result.current.error).toBe(false);
  expect(getLeaderboard).toHaveBeenCalledWith('livetruth');
});

it('treats a null result as an error, distinct from an empty entries list', async () => {
  getLeaderboard.mockResolvedValue(null);
  const { result } = renderHook(() => useLeaderboard('livetruth'));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.data).toBeNull();
  expect(result.current.error).toBe(true);
});

it('treats a rejected IPC call as an error rather than throwing', async () => {
  getLeaderboard.mockRejectedValue(new Error('ipc down'));
  const { result } = renderHook(() => useLeaderboard('livetruth'));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBe(true);
});

it('re-fetches when benchmarkId changes', async () => {
  getLeaderboard.mockResolvedValue(DATA);
  const { result, rerender } = renderHook(({ id }) => useLeaderboard(id), {
    initialProps: { id: 'livetruth' as string | null },
  });
  await waitFor(() => expect(result.current.loading).toBe(false));

  rerender({ id: 'hle' });
  await waitFor(() => expect(getLeaderboard).toHaveBeenCalledWith('hle'));
  expect(getLeaderboard).toHaveBeenCalledTimes(2);
});

it('refresh() re-fetches the current benchmark on demand', async () => {
  getLeaderboard.mockResolvedValue(DATA);
  const { result } = renderHook(() => useLeaderboard('livetruth'));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(getLeaderboard).toHaveBeenCalledTimes(1);

  act(() => result.current.refresh());
  await waitFor(() => expect(getLeaderboard).toHaveBeenCalledTimes(2));
});
