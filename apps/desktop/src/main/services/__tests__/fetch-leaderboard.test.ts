import { vi, describe, it, expect, afterEach } from 'vitest';

// Mirror list-benchmarks.test: stub context (URLs) + publish-log (pulls in electron).
const CTX = {
  scoreboardUrl: 'https://scoreboard.screamingface.ai',
  portalUrl: 'https://screamingface.ai/portal/',
  client: { name: 'screamingface-desktop', version: '0.4.2', platform: 'darwin' },
};
vi.mock('../publish-context', () => ({ resolvePublishContext: () => CTX }));
vi.mock('../publish-log', () => ({ publishLog: () => {} }));

import { listLeaderboard } from '../fetch-leaderboard';

const BENCHMARK = {
  id: 'livetruth',
  display_name: 'LiveTruth',
  description: 'Sample benchmark for local dev',
  dataset_url: null,
};

const ENTRY = {
  rank: 1,
  spec_id: 'local-smoke',
  accuracy: 0.5,
  total_questions: 2,
  ran_with_providers: ['smoke'],
  submitted_at: '2026-07-07T15:30:05.108456Z',
  submitted_by: 'filip-local',
  verified_by_openmined: false,
  url4_expression: 'url4://smoke',
};

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('listLeaderboard (main process)', () => {
  it('hits GET /v1/leaderboard/{id} on the configured scoreboard and maps benchmark + entries', async () => {
    const fetchMock = vi.fn(async () => okResponse({ benchmark: BENCHMARK, entries: [ENTRY] }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const out = await listLeaderboard('livetruth');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      'https://scoreboard.screamingface.ai/v1/leaderboard/livetruth',
    );
    expect(out).toEqual({
      benchmark: {
        id: 'livetruth',
        displayName: 'LiveTruth',
        description: 'Sample benchmark for local dev',
        datasetUrl: null,
      },
      entries: [
        {
          rank: 1,
          specId: 'local-smoke',
          accuracy: 0.5,
          totalQuestions: 2,
          ranWithProviders: ['smoke'],
          submittedAt: '2026-07-07T15:30:05.108456Z',
          submittedBy: 'filip-local',
          verifiedByOpenmined: false,
          url4Expression: 'url4://smoke',
        },
      ],
    });
  });

  it('appends ?top= when provided', async () => {
    const fetchMock = vi.fn(async () => okResponse({ benchmark: BENCHMARK, entries: [] }));
    global.fetch = fetchMock as unknown as typeof fetch;

    await listLeaderboard('livetruth', 10);

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      'https://scoreboard.screamingface.ai/v1/leaderboard/livetruth?top=10',
    );
  });

  it('drops a malformed entry rather than throwing, keeping the well-formed ones', async () => {
    global.fetch = vi.fn(async () =>
      okResponse({
        benchmark: BENCHMARK,
        entries: [ENTRY, { ...ENTRY, rank: 2, accuracy: 'not-a-number' }],
      }),
    ) as unknown as typeof fetch;

    const out = await listLeaderboard('livetruth');

    expect(out?.entries).toHaveLength(1);
    expect(out?.entries[0].rank).toBe(1);
  });

  it('returns null when the benchmark field is missing/malformed', async () => {
    global.fetch = vi.fn(async () => okResponse({ entries: [ENTRY] })) as unknown as typeof fetch;
    expect(await listLeaderboard('livetruth')).toBeNull();
  });

  it('returns null on a non-2xx response (e.g. unknown benchmark 404)', async () => {
    global.fetch = vi.fn(
      async () => ({ ok: false, status: 404 }) as unknown as Response,
    ) as unknown as typeof fetch;
    expect(await listLeaderboard('unknown-benchmark')).toBeNull();
  });

  it('returns null when the scoreboard is unreachable', async () => {
    global.fetch = vi.fn(async () => {
      throw new Error('network down');
    }) as unknown as typeof fetch;
    expect(await listLeaderboard('livetruth')).toBeNull();
  });

  it('aborts and returns null after the 8s timeout', async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn(
      (_url, opts?: { signal?: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          opts?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    ) as unknown as typeof fetch;

    const promise = listLeaderboard('livetruth');
    await vi.advanceTimersByTimeAsync(8_000);
    const out = await promise;

    expect(out).toBeNull();
  });

  it('builds the URL from resolvePublishContext, not a hardcoded host', async () => {
    CTX.scoreboardUrl = 'http://localhost:9106';
    const fetchMock = vi.fn(async () => okResponse({ benchmark: BENCHMARK, entries: [] }));
    global.fetch = fetchMock as unknown as typeof fetch;

    await listLeaderboard('livetruth');

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      'http://localhost:9106/v1/leaderboard/livetruth',
    );
    CTX.scoreboardUrl = 'https://scoreboard.screamingface.ai';
  });
});
