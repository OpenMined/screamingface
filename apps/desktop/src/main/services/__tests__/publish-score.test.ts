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
// publish-log transitively imports electron (debug-log) at module load — stub it.
vi.mock('../publish-log', () => ({ publishLog: () => {} }));

import { submitScore } from '../publish-score';

const REQUEST: PublishScoreRequest = {
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
};

function okResponse(): Response {
  return {
    ok: true,
    status: 201,
    json: async () => ({ id: 'score-1', benchmark_id: 'hle', spec_id: 'hle-ensemble-three' }),
  } as unknown as Response;
}

function errResponse(status: number, body = 'rejected'): Response {
  return {
    ok: false,
    status,
    text: async () => body,
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
    // SF-300: content signature carried as free-form metadata for server-side verification.
    expect(body.metadata).toEqual({ benchmark_signature: 'a'.repeat(64), signature_alg: 'sha256' });

    expect(outcome).toEqual({
      ok: true,
      value: {
        id: 'score-1',
        benchmarkId: 'hle',
        specId: 'hle-ensemble-three',
        portalLink: 'https://scoreboard.screamingface.ai/benchmark.html?id=hle',
      },
    });
  });

  it('sends metadata=null when there is no benchmark signature', async () => {
    const fetchMock = vi.fn(async () => okResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    await submitScore({ ...REQUEST, benchmarkSignature: '' });

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.metadata).toBeNull();
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

  it('surfaces the FastAPI 422 validator detail instead of a generic "report it" message', async () => {
    // Real scoreboard shape: detail is an array of {loc, msg}.
    const body = JSON.stringify({
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'total_questions'],
          msg: 'Value error, total_questions must be positive',
        },
      ],
    });
    global.fetch = vi.fn(async () => errResponse(422, body)) as unknown as typeof fetch;

    const outcome = await submitScore({ ...REQUEST, totalQuestions: 0, correctQuestions: 0 });

    expect(outcome.ok).toBe(false);
    if (!outcome.ok) {
      expect(outcome.error).toContain('total_questions must be positive');
      expect(outcome.error).not.toMatch(/please report it/i);
    }
  });

  it('surfaces the 400 FieldErrorResponse message (accuracy mismatch)', async () => {
    const body = JSON.stringify({
      detail: { field: 'accuracy', message: 'accuracy 0.9 does not match correct/total=0.81' },
    });
    global.fetch = vi.fn(async () => errResponse(400, body)) as unknown as typeof fetch;

    const outcome = await submitScore(REQUEST);

    expect(outcome.ok).toBe(false);
    if (!outcome.ok) expect(outcome.error).toContain('does not match');
  });

  it('falls back to generic copy when the error body is not JSON', async () => {
    global.fetch = vi.fn(async () =>
      errResponse(422, '<html>502 bad gateway</html>'),
    ) as unknown as typeof fetch;

    const outcome = await submitScore(REQUEST);

    expect(outcome.ok).toBe(false);
    if (!outcome.ok) expect(outcome.error).toMatch(/did not match the scoreboard contract/i);
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
