// apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts
// @vitest-environment jsdom
import { renderHook, act, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const fetchMock = vi.fn();

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({
    status: 'ready',
    info: { scheme: 'http', host: '127.0.0.1', port: 8001 },
  }),
}));

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    server: { fetch: fetchMock },
  };
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  cleanup();
});

import { useEvalRun } from './use-eval-run';

const payload = { spec: 'HLE', expression: 'transform(url, intent)' };

it('fires /ensemble with run headers and polls /eval_runs to done', async () => {
  fetchMock
    .mockResolvedValueOnce({ ok: false, status: 0, body: '' }) // ensemble (times out, ignored)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: JSON.stringify({ status: 'running', correct_questions: 1, total_questions: 4 }),
    })
    .mockResolvedValue({
      ok: true,
      status: 200,
      body: JSON.stringify({
        status: 'done',
        accuracy: 0.75,
        correct_questions: 3,
        total_questions: 4,
      }),
    });

  const { result } = renderHook(() => useEvalRun(payload));
  expect(result.current.runState).toBe('idle');

  act(() => result.current.startRun());
  expect(result.current.runState).toBe('running');

  const ensembleCall = fetchMock.mock.calls[0];
  expect(ensembleCall[0]).toContain('/ensemble?q=');
  expect(ensembleCall[1].headers['X-SF-Run-Spec']).toBe('HLE');
  expect(ensembleCall[1].headers['X-SF-Run-Id']).toBeTruthy();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  await waitFor(() => expect(result.current.runState).toBe('done'));
  expect(result.current.run?.accuracy).toBe(0.75);
});

it('does not mark failed when the ensemble fetch rejects (run drives state via poll)', async () => {
  fetchMock
    .mockRejectedValueOnce(new Error('timeout')) // ensemble
    .mockResolvedValue({
      ok: true,
      status: 200,
      body: JSON.stringify({ status: 'running', total_questions: 4, correct_questions: 0 }),
    });

  const { result } = renderHook(() => useEvalRun(payload));
  await act(async () => {
    result.current.startRun();
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(result.current.runState).toBe('running');
});

it('mints a fresh run_id when an edited expression override is supplied', async () => {
  fetchMock.mockResolvedValue({ ok: false, status: 0, body: '' });
  const pinned = { spec: 'HLE', expression: 'a(b)', runId: 'pinned-id' };
  const { result } = renderHook(() => useEvalRun(pinned));

  // No override -> reuses the pinned deep-link run id.
  act(() => result.current.startRun());
  const plainCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/ensemble?q='));
  expect(plainCall?.[1].headers['X-SF-Run-Id']).toBe('pinned-id');

  // Override (edited expression) -> fresh id, never the pinned one.
  act(() => result.current.startRun('edited(expr)'));
  const editedCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('edited'));
  const editedId = editedCall?.[1].headers['X-SF-Run-Id'];
  expect(editedId).toBeTruthy();
  expect(editedId).not.toBe('pinned-id');
});
