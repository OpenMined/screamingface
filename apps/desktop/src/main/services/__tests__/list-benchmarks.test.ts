import { vi, describe, it, expect, afterEach } from 'vitest';

// Mirror publish-score.test: stub context (URLs) + publish-log (pulls in electron).
const CTX = {
  scoreboardUrl: 'https://scoreboard.screamingface.ai',
  portalUrl: 'https://screamingface.ai/portal/',
  client: { name: 'screamingface-desktop', version: '0.4.2', platform: 'darwin' },
};
vi.mock('../publish-context', () => ({ resolvePublishContext: () => CTX }));
vi.mock('../publish-log', () => ({ publishLog: () => {} }));

import { listBenchmarks } from '../list-benchmarks';

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('listBenchmarks (main process)', () => {
  it('hits GET /v1/benchmarks on the configured scoreboard and maps the rows', async () => {
    const fetchMock = vi.fn(async () =>
      okResponse({
        benchmarks: [
          { id: 'honest-agi-live-week-3', display_name: 'Honest AGI Live week 3' },
          { id: 'hle', display_name: 'HLE' },
        ],
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const out = await listBenchmarks();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      'https://scoreboard.screamingface.ai/v1/benchmarks',
    );
    expect(out).toEqual([
      { id: 'honest-agi-live-week-3', displayName: 'Honest AGI Live week 3' },
      { id: 'hle', displayName: 'HLE' },
    ]);
  });

  it('falls back to id when display_name is missing, and drops rows without an id', async () => {
    global.fetch = vi.fn(async () =>
      okResponse({ benchmarks: [{ id: 'gpqa' }, { display_name: 'no id' }, { id: '' }] }),
    ) as unknown as typeof fetch;

    const out = await listBenchmarks();

    expect(out).toEqual([{ id: 'gpqa', displayName: 'gpqa' }]);
  });

  it('returns null on a non-2xx response (so callers show no false "unknown")', async () => {
    global.fetch = vi.fn(
      async () => ({ ok: false, status: 503 }) as unknown as Response,
    ) as unknown as typeof fetch;
    expect(await listBenchmarks()).toBeNull();
  });

  it('returns null when the registry is unreachable', async () => {
    global.fetch = vi.fn(async () => {
      throw new Error('network down');
    }) as unknown as typeof fetch;
    expect(await listBenchmarks()).toBeNull();
  });
});
