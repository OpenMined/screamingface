import { describe, expect, it, vi } from 'vitest';

import { runImportProfile } from '../codex-import-launcher';

describe('runImportProfile', () => {
  it('posts to the backend import route with profile name', async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ ok: true }), { status: 201 }),
    );

    const result = await runImportProfile({
      sfBaseUrl: 'http://127.0.0.1:8000',
      backendName: 'codex',
      profileName: 'default',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8000/codex/auth/import?name=default', {
      method: 'POST',
    });
  });

  it('returns structured failure when import route fails', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: { code: 'auth_required', message: 'missing' } }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        }),
    );

    const result = await runImportProfile({
      sfBaseUrl: 'http://127.0.0.1:8000',
      backendName: 'codex',
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(result).toEqual({ ok: false, status: 401, message: 'missing' });
  });
});
