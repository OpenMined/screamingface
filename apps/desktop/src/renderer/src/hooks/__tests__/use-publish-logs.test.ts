// @vitest-environment jsdom
import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { usePublishLogs } from '../use-publish-logs';

let onLogCb: ((line: string) => void) | null = null;
const unsub = vi.fn();

beforeEach(() => {
  onLogCb = null;
  unsub.mockClear();
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: {
      getLogs: vi.fn(async () => ['[t0] publish: backlog line']),
      onLog: vi.fn((cb: (line: string) => void) => {
        onLogCb = cb;
        return unsub;
      }),
    },
  };
});

afterEach(() => vi.restoreAllMocks());

describe('usePublishLogs', () => {
  it('loads the backlog then appends live lines', async () => {
    const { result } = renderHook(() => usePublishLogs());

    await waitFor(() => expect(result.current.logs).toHaveLength(1));
    expect(result.current.logs[0]).toContain('backlog');

    act(() => onLogCb?.('[t1] publish: attempt 1/4 -> HTTP 404'));
    expect(result.current.logs).toHaveLength(2);
    expect(result.current.logs[1]).toContain('HTTP 404');
  });

  it('clears and unsubscribes on unmount', async () => {
    const { result, unmount } = renderHook(() => usePublishLogs());
    await waitFor(() => expect(result.current.logs.length).toBeGreaterThan(0));

    act(() => result.current.clearLogs());
    expect(result.current.logs).toEqual([]);

    unmount();
    expect(unsub).toHaveBeenCalledTimes(1);
  });
});
