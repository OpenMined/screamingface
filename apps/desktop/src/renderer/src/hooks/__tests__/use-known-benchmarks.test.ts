// @vitest-environment jsdom
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach, beforeEach } from 'vitest';
import { useKnownBenchmarks } from '../use-known-benchmarks';

const listBenchmarks = vi.fn();

beforeEach(() => {
  listBenchmarks.mockReset();
  (window as unknown as { electronAPI: unknown }).electronAPI = { publish: { listBenchmarks } };
});
afterEach(cleanup);

it('starts loading, then resolves the registry list', async () => {
  listBenchmarks.mockResolvedValue([{ id: 'hle', displayName: 'HLE' }]);
  const { result } = renderHook(() => useKnownBenchmarks());
  expect(result.current.loading).toBe(true);
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.benchmarks).toEqual([{ id: 'hle', displayName: 'HLE' }]);
});

it('resolves to null (not loading) when the registry is unreachable', async () => {
  listBenchmarks.mockResolvedValue(null);
  const { result } = renderHook(() => useKnownBenchmarks());
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.benchmarks).toBeNull();
});

it('treats a rejected IPC call as unavailable rather than throwing', async () => {
  listBenchmarks.mockRejectedValue(new Error('ipc down'));
  const { result } = renderHook(() => useKnownBenchmarks());
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.benchmarks).toBeNull();
});
