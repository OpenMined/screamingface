// @vitest-environment jsdom
import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { usePublishScore, type PublishInputs } from '../use-publish-score';
import type { EvalRunDetail } from '@/components/eval/types';

const CTX = {
  scoreboardUrl: 'https://scoreboard.screamingface.ai',
  portalUrl: 'http://localhost:8080',
  client: { name: 'screamingface-desktop', version: '0.4.2', platform: 'darwin' },
};

const RUN: EvalRunDetail = {
  id: 'eval-run-abc123',
  spec_name: 'hle:hle-ensemble-three',
  url4_expression: 'url4://ensemble(claude,codex,gemini)/hle',
  started_at: '2026-05-04T11:00:00Z',
  finished_at: '2026-05-04T11:55:00Z',
  status: 'done',
  accuracy: 0.81,
  total_questions: 1000,
  correct_questions: 810,
  error: null,
  favorite: false,
  questions: [],
};

const INPUTS: PublishInputs = {
  run: RUN,
  benchmarkId: 'hle',
  specId: 'hle-ensemble-three',
  url4Expression: RUN.url4_expression,
  providers: ['claude', 'codex', 'gemini'],
  submittedBy: null,
};

function okResponse(): Response {
  return {
    ok: true,
    status: 201,
    json: async () => ({ id: 'score-1', benchmark_id: 'hle', spec_id: 'hle-ensemble-three' }),
  } as unknown as Response;
}

function errResponse(status: number): Response {
  return {
    ok: false,
    status,
    text: async () => 'rejected',
    json: async () => ({}),
  } as unknown as Response;
}

beforeEach(() => {
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: { getContext: vi.fn(async () => CTX), openExternal: vi.fn(async () => {}) },
  };
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('usePublishScore', () => {
  it('POSTs the nested-client wire shape with the eval_run id as Idempotency-Key', async () => {
    const fetchMock = vi.fn(async () => okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    const { result } = renderHook(() => usePublishScore());
    let out: Awaited<ReturnType<typeof result.current.publish>> = null;
    await act(async () => {
      out = await result.current.publish(INPUTS);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://scoreboard.screamingface.ai/v1/scores');
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('eval-run-abc123');
    const body = JSON.parse(init.body as string);
    // Nested client, not flat — and recomputed accuracy = correct/total.
    expect(body.client).toEqual({
      name: 'screamingface-desktop',
      version: '0.4.2',
      platform: 'darwin',
    });
    expect(body).not.toHaveProperty('client_name');
    expect(body.accuracy).toBeCloseTo(0.81, 5);
    expect(body.ran_with_providers).toEqual(['claude', 'codex', 'gemini']);
    expect(body.submitted_by).toBeNull();
    expect(body.ran_at_local).toBe('2026-05-04T11:55:00Z');

    expect(result.current.status).toBe('success');
    expect(out).toMatchObject({
      id: 'score-1',
      portalLink: 'http://localhost:8080/spec.html?benchmark=hle&spec=hle-ensemble-three',
    });
  });

  it('recomputes accuracy from totals (ignores a stale stored value)', async () => {
    const fetchMock = vi.fn(async () => okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;
    const drifted: PublishInputs = {
      ...INPUTS,
      run: { ...RUN, accuracy: 0.9, correct_questions: 810, total_questions: 1000 },
    };
    const { result } = renderHook(() => usePublishScore());
    await act(async () => {
      await result.current.publish(drifted);
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.accuracy).toBeCloseTo(0.81, 5); // 810/1000, not the stored 0.9
  });

  it('does not retry a 4xx and surfaces actionable copy', async () => {
    const fetchMock = vi.fn(async () => errResponse(404));
    global.fetch = fetchMock as unknown as typeof fetch;

    const { result } = renderHook(() => usePublishScore());
    await act(async () => {
      await result.current.publish(INPUTS);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/not registered/i);
  });

  it('retries a transient network failure with backoff, then succeeds', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    const { result } = renderHook(() => usePublishScore());
    await act(async () => {
      const promise = result.current.publish(INPUTS);
      await vi.advanceTimersByTimeAsync(1100); // first backoff = 1s
      await promise;
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('success');
  });
});
