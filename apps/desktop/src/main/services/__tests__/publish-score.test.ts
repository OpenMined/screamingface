import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import type { PublishScoreRequest } from '../../../preload/types';

// The service reads URLs + client via resolvePublishContext; stub it so the
// test is independent of env/sf.json and asserts against fixed prod-shaped URLs.
const CTX = {
  scoreboardUrl: 'https://scoreboard.screamingface.ai',
  portalUrl: 'https://screamingface.ai/portal/',
  client: { name: 'screamingface-desktop', version: '0.4.2', platform: 'darwin' },
};
vi.mock('../publish-context', () => ({ resolvePublishContext: () => CTX }));

import { submitScore } from '../publish-score';

const REQUEST: PublishScoreRequest = {
  benchmarkId: 'hle',
  specId: 'hle-ensemble-three',
  url4Expression: 'url4://ensemble(claude,codex,gemini)/hle',
  providers: ['claude', 'codex', 'gemini'],
  submittedBy: null,
  runId: 'eval-run-abc123',
  totalQuestions: 1000,
  correctQuestions: 810,
  ranAtLocal: '2026-05-04T11:55:00Z',
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

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('submitScore (main process)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('POSTs the nested-client wire shape to the prod scoreboard with the run id as Idempotency-Key', async () => {
    const fetchMock = vi.fn(async () => okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    const outcome = await submitScore(REQUEST);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
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

    expect(outcome).toEqual({
      ok: true,
      value: {
        id: 'score-1',
        benchmarkId: 'hle',
        specId: 'hle-ensemble-three',
        portalLink:
          'https://screamingface.ai/portal/spec.html?benchmark=hle&spec=hle-ensemble-three',
      },
    });
  });

  it('recomputes accuracy from totals (ignores any drift)', async () => {
    const fetchMock = vi.fn(async () => okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    await submitScore({ ...REQUEST, correctQuestions: 810, totalQuestions: 1000 });

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.accuracy).toBeCloseTo(0.81, 5); // 810/1000
  });

  it('does not retry a 4xx and returns actionable copy', async () => {
    const fetchMock = vi.fn(async () => errResponse(404));
    global.fetch = fetchMock as unknown as typeof fetch;

    const outcome = await submitScore(REQUEST);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) expect(outcome.error).toMatch(/not registered/i);
  });

  it('retries a transient network failure with backoff, then succeeds', async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    const promise = submitScore(REQUEST);
    await vi.advanceTimersByTimeAsync(1100); // first backoff = 1s
    const outcome = await promise;

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(outcome.ok).toBe(true);
  });
});
