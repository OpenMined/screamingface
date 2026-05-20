import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

// Hoisted mock of electron — must be declared before importing the SUT
const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('electron', () => ({ shell: { openExternal } }));

import {
  clearPendingAuthState,
  clearPendingConnectionAuthState,
  getPendingAuthState,
  getPendingConnectionAuthState,
  runOAuthConnectionLauncher,
  runOAuthLauncher,
} from '../oauth-launcher';

const AUTHORIZE_URL =
  'https://claude.com/cai/oauth/authorize?' +
  new URLSearchParams({
    response_type: 'code',
    client_id: 'public-client-id',
    redirect_uri: 'http://localhost:9105/callback',
    scope: 'read write',
    code_challenge: 'challenge',
    code_challenge_method: 'S256',
    state: 's1',
  }).toString();

const ALTERNATE_AUTHORIZE_URL =
  'https://auth.openai.com/oauth/authorize?' +
  new URLSearchParams({
    response_type: 'code',
    client_id: 'alternate-public-client-id',
    redirect_uri: 'http://localhost:1455/auth/callback',
    scope: 'openid profile',
    code_challenge: 'challenge',
    code_challenge_method: 'S256',
    state: 's1',
  }).toString();

const EXTERNAL_CLAUDE_AUTHORIZE_URL =
  'https://claude.com/cai/oauth/authorize?' +
  new URLSearchParams({
    response_type: 'code',
    client_id: 'public-client-id',
    redirect_uri: 'http://localhost:9106/callback',
    scope: 'read write',
    code_challenge: 'challenge',
    code_challenge_method: 'S256',
    state: 's1',
  }).toString();

beforeEach(() => {
  openExternal.mockClear();
  clearPendingAuthState('browser-backend');
  clearPendingAuthState('browser-backend', 'work');
  clearPendingAuthState('browser-backend', 'personal');
  clearPendingConnectionAuthState('browser-backend', '00000000-0000-0000-0000-000000000001');
  clearPendingAuthState('other-backend');
});
afterEach(() => {
  vi.useRealTimers();
});

function makeFetch(responses: Array<() => Response>): ReturnType<typeof vi.fn> {
  const seq = [...responses];
  return vi.fn(async () => {
    const next = seq.shift();
    if (!next) throw new Error('fetch called more times than mocked');
    return next();
  });
}

describe('runOAuthLauncher', () => {
  it('opens the authorize URL and resolves on AUTHENTICATED status', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 's1' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      () =>
        new Response(JSON.stringify({ state: 'pending' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      () =>
        new Response(JSON.stringify({ state: 'authenticated' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(openExternal).toHaveBeenCalledWith(AUTHORIZE_URL);
    expect(result.kind).toBe('complete');
  });

  it('opens another safe authorize URL for another backend slug', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: ALTERNATE_AUTHORIZE_URL, state: 's1' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      () =>
        new Response(JSON.stringify({ state: 'authenticated' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'other-backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(openExternal).toHaveBeenCalledWith(ALTERNATE_AUTHORIZE_URL);
    expect(result.kind).toBe('complete');
  });

  it('returns timeout when status never reaches authenticated', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 's1' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ...Array(20).fill(
        () =>
          new Response(JSON.stringify({ state: 'pending' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
      ),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 10,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('timeout');
  });

  it('short-circuits to provider_error when status is error', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 's1' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      () =>
        new Response(JSON.stringify({ state: 'error', error: 'bad code' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ]);
    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('provider_error');
  });

  it('forwards profileName as ?name= on both start and status URLs', async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      calls.push(url);
      if (calls.length === 1) {
        return new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 's1' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ state: 'authenticated' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    });

    await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      profileName: 'work',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(calls[0]).toBe('http://127.0.0.1:1234/browser-backend/auth/start?name=work');
    expect(calls[1]).toBe('http://127.0.0.1:1234/browser-backend/auth/status?name=work');
  });

  it('keeps pending auth states scoped by backend and profile', async () => {
    const workFetch = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 'state-work' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ]);
    const personalFetch = makeFetch([
      () =>
        new Response(JSON.stringify({ authorize_url: AUTHORIZE_URL, state: 'state-personal' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ]);

    await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      profileName: 'work',
      timeoutMs: 0,
      fetchImpl: workFetch as unknown as typeof fetch,
    });
    await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      profileName: 'personal',
      timeoutMs: 0,
      fetchImpl: personalFetch as unknown as typeof fetch,
    });

    expect(getPendingAuthState('browser-backend', 'work')).toBe('state-work');
    expect(getPendingAuthState('browser-backend', 'personal')).toBe('state-personal');
  });

  it('returns gateway_error when /auth/start returns 502', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ detail: { code: 'gateway_unreachable' } }), {
          status: 502,
          headers: { 'content-type': 'application/json' },
        }),
    ]);
    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(openExternal).not.toHaveBeenCalled();
    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('gateway_error');
  });

  it('rejects invalid browser OAuth backend slugs before calling SF', async () => {
    const fetchMock = vi.fn();

    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: '../backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(openExternal).not.toHaveBeenCalled();
    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('gateway_error');
  });

  it('rejects unexpected authorize URLs from SF', async () => {
    const maliciousAuthorizeUrl =
      'https://identity.example.test/oauth/authorize?' +
      new URLSearchParams({
        response_type: 'code',
        client_id: 'public-client-id',
        redirect_uri: 'http://localhost:9105/auth/callback',
        scope: 'read write',
        code_challenge: 'challenge',
        code_challenge_method: 'S256',
        state: 's1',
      }).toString();
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({
            authorize_url: maliciousAuthorizeUrl,
            state: 's1',
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' },
          },
        ),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(openExternal).not.toHaveBeenCalled();
    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('gateway_error');
  });

  it('opens connection authorize URL and resolves with duplicate metadata', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({
            connection_id: '00000000-0000-0000-0000-000000000001',
            authorize_url: AUTHORIZE_URL,
            state: 'connection-state',
          }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        ),
      () =>
        new Response(
          JSON.stringify({
            id: '00000000-0000-0000-0000-000000000111',
            label: 'codex@example.com',
            status: 'active',
            is_duplicate: true,
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
    ]);

    const result = await runOAuthConnectionLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      label: 'work-anthropic',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(openExternal).toHaveBeenCalledWith(AUTHORIZE_URL);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://127.0.0.1:1234/browser-backend/auth/connections',
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ label: 'work-anthropic' }),
      },
    );
    expect(result.kind).toBe('complete');
    if (result.kind === 'complete') {
      expect(result.isDuplicate).toBe(true);
      expect(result.connection?.id).toBe('00000000-0000-0000-0000-000000000111');
    }
    expect(
      getPendingConnectionAuthState('browser-backend', '00000000-0000-0000-0000-000000000001'),
    ).toBeNull();
  });

  it('keeps pending connection state available after connection OAuth timeout', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({
            connection_id: '00000000-0000-0000-0000-000000000001',
            authorize_url: AUTHORIZE_URL,
            state: 'connection-state',
          }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        ),
      ...Array(20).fill(
        () =>
          new Response(
            JSON.stringify({
              id: '00000000-0000-0000-0000-000000000001',
              label: 'work-anthropic',
              status: 'pending',
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
      ),
    ]);

    const result = await runOAuthConnectionLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 10,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.reason).toBe('timeout');
    expect(
      getPendingConnectionAuthState('browser-backend', '00000000-0000-0000-0000-000000000001'),
    ).toBe('connection-state');
  });

  it('allows connection OAuth through the supplied external gateway redirect port', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({
            connection_id: '00000000-0000-0000-0000-000000000001',
            authorize_url: EXTERNAL_CLAUDE_AUTHORIZE_URL,
            state: 'connection-state',
          }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        ),
      () =>
        new Response(
          JSON.stringify({
            id: '00000000-0000-0000-0000-000000000001',
            label: 'work-anthropic',
            status: 'active',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
    ]);

    const result = await runOAuthConnectionLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      label: 'work-anthropic',
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
      allowedOAuthRedirectPorts: ['9106'],
    });

    expect(openExternal).toHaveBeenCalledWith(EXTERNAL_CLAUDE_AUTHORIZE_URL);
    expect(result.kind).toBe('complete');
  });

  it('rejects unsafe connection ids before opening browser or polling', async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({
            connection_id: '../auth/profiles/default',
            authorize_url: AUTHORIZE_URL,
            state: 'connection-state',
          }),
          { status: 201, headers: { 'content-type': 'application/json' } },
        ),
    ]);

    const result = await runOAuthConnectionLauncher({
      sfBaseUrl: 'http://127.0.0.1:1234',
      backendName: 'browser-backend',
      pollIntervalMs: 1,
      timeoutMs: 10,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result.kind).toBe('failed');
    if (result.kind === 'failed') expect(result.message).toBe('invalid connection id');
    expect(openExternal).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
