// @vitest-environment jsdom
import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { usePublishScore, type PublishInputs } from '../use-publish-score';
import type { EvalRunDetail } from '@/components/eval/types';
import type { PublishOutcome } from '../../../../preload/types';

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
  benchmarkSignature: 'a'.repeat(64),
  specId: 'hle-ensemble-three',
  url4Expression: RUN.url4_expression,
  providers: ['claude', 'codex', 'gemini'],
  submittedBy: null,
};

const SUCCESS: PublishOutcome = {
  ok: true,
  value: {
    id: 'score-1',
    benchmarkId: 'hle',
    specId: 'hle-ensemble-three',
    portalLink: 'https://scoreboard.screamingface.ai/benchmark.html?id=hle',
  },
};

let submitScore: ReturnType<typeof vi.fn>;

beforeEach(() => {
  submitScore = vi.fn(async () => SUCCESS);
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    publish: { submitScore, openExternal: vi.fn(async () => {}) },
  };
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('usePublishScore', () => {
  it('flattens the run into the IPC request (idempotency id, totals, ran_at) and returns the value on success', async () => {
    const { result } = renderHook(() => usePublishScore());
    let out: Awaited<ReturnType<typeof result.current.publish>> = null;
    await act(async () => {
      out = await result.current.publish(INPUTS);
    });

    expect(submitScore).toHaveBeenCalledTimes(1);
    expect(submitScore).toHaveBeenCalledWith({
      benchmarkId: 'hle',
      benchmarkSignature: 'a'.repeat(64),
      specId: 'hle-ensemble-three',
      url4Expression: 'url4://ensemble(claude,codex,gemini)/hle',
      providers: ['claude', 'codex', 'gemini'],
      submittedBy: null,
      runId: 'eval-run-abc123',
      totalQuestions: 1000,
      correctQuestions: 810,
      ranAtLocal: '2026-05-04T11:55:00Z',
    });
    expect(result.current.status).toBe('success');
    expect(out).toEqual(SUCCESS.value);
    expect(result.current.result).toEqual(SUCCESS.value);
  });

  it('falls back to started_at when the run has no finished_at', async () => {
    const { result } = renderHook(() => usePublishScore());
    await act(async () => {
      await result.current.publish({ ...INPUTS, run: { ...RUN, finished_at: null } });
    });
    const sent = submitScore.mock.calls[0][0] as { ranAtLocal: string };
    expect(sent.ranAtLocal).toBe('2026-05-04T11:00:00Z');
  });

  it('surfaces the error string from a failed outcome without throwing', async () => {
    submitScore.mockResolvedValueOnce({
      ok: false,
      error: 'That benchmark is not registered on the scoreboard yet.',
    } satisfies PublishOutcome);

    const { result } = renderHook(() => usePublishScore());
    let out: Awaited<ReturnType<typeof result.current.publish>> = 'sentinel' as never;
    await act(async () => {
      out = await result.current.publish(INPUTS);
    });

    expect(out).toBeNull();
    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/not registered/i);
  });

  it('maps a thrown IPC error to error state', async () => {
    submitScore.mockRejectedValueOnce(new Error('ipc exploded'));
    const { result } = renderHook(() => usePublishScore());
    await act(async () => {
      await result.current.publish(INPUTS);
    });
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('ipc exploded');
  });
});
