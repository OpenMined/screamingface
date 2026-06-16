import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createPrivate,
  deletePrivate,
  getPrivateContent,
  listPrivate,
  updatePrivate,
} from '../private-data-api';

const base = 'http://localhost:9100';

// electronAPI.server.fetch resolves to `{ ok, status, body }` (raw text body),
// not a WHATWG Response — mirror that shape here (see preload/types.ts).
function mockFetch(status: number, body: string) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    body,
  });
  // @ts-expect-error test shim
  globalThis.window = { electronAPI: { server: { fetch: fetchMock } } };
  return fetchMock;
}

afterEach(() => vi.restoreAllMocks());

describe('private-data-api', () => {
  it('lists entities', async () => {
    const f = mockFetch(200, JSON.stringify([{ uuid: 'u1', label: 'a', updated_at: 't' }]));
    const rows = await listPrivate(base);
    expect(rows).toEqual([{ uuid: 'u1', label: 'a', updated_at: 't' }]);
    expect(f).toHaveBeenCalledWith(`${base}/private`, expect.objectContaining({ method: 'GET' }));
  });

  it('creates with label+content', async () => {
    const f = mockFetch(200, JSON.stringify({ uuid: 'u2', url: '/private/u2', label: 'x' }));
    const res = await createPrivate(base, { label: 'x', content: '# hi' });
    expect(res.uuid).toBe('u2');
    const [, init] = f.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ label: 'x', content: '# hi' });
  });

  it('gets raw content', async () => {
    mockFetch(200, '# raw');
    expect(await getPrivateContent(base, 'u1')).toBe('# raw');
  });

  it('updates and deletes', async () => {
    const f = mockFetch(200, JSON.stringify({ uuid: 'u1', label: 'y' }));
    await updatePrivate(base, 'u1', { content: '# z' });
    await deletePrivate(base, 'u1');
    expect(f).toHaveBeenLastCalledWith(
      `${base}/private/u1`,
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('throws on non-ok', async () => {
    mockFetch(404, '');
    await expect(getPrivateContent(base, 'missing')).rejects.toThrow();
  });
});
