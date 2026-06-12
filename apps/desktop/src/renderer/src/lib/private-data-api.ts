// Pure HTTP wrappers around the private-storage plugin (/private). All calls go
// through window.electronAPI.server.fetch against the running local server base
// (`${scheme}://${host}:${port}`). Keep UI/state concerns out of this module.
//
// Note: electronAPI.server.fetch resolves to `{ ok, status, body }` where `body`
// is the raw response text (see preload/types.ts), not a WHATWG Response — so we
// parse JSON from `body` ourselves rather than calling `.json()` / `.text()`.

export interface PrivateItem {
  uuid: string;
  label: string | null;
  updated_at: string;
}

export interface CreateResult {
  uuid: string;
  url: string;
  label: string | null;
}

function api() {
  return window.electronAPI.server;
}

async function ok(res: { ok: boolean; status: number }, what: string): Promise<void> {
  if (!res.ok) throw new Error(`${what} failed (HTTP ${res.status})`);
}

export async function listPrivate(base: string): Promise<PrivateItem[]> {
  const res = await api().fetch(`${base}/private`, { method: 'GET' });
  await ok(res, 'list');
  return JSON.parse(res.body || '[]') as PrivateItem[];
}

export async function createPrivate(
  base: string,
  payload: { label?: string | null; content?: string },
): Promise<CreateResult> {
  const res = await api().fetch(`${base}/private`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: payload.label ?? null, content: payload.content ?? '' }),
  });
  await ok(res, 'create');
  return JSON.parse(res.body || '{}') as CreateResult;
}

export async function getPrivateContent(base: string, uuid: string): Promise<string> {
  const res = await api().fetch(`${base}/private/${uuid}`, { method: 'GET' });
  await ok(res, 'get');
  return res.body;
}

export async function updatePrivate(
  base: string,
  uuid: string,
  payload: { label?: string | null; content?: string },
): Promise<void> {
  const body: Record<string, unknown> = {};
  if (payload.content !== undefined) body.content = payload.content;
  if (payload.label !== undefined) body.label = payload.label;
  const res = await api().fetch(`${base}/private/${uuid}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  await ok(res, 'update');
}

export async function deletePrivate(base: string, uuid: string): Promise<void> {
  const res = await api().fetch(`${base}/private/${uuid}`, { method: 'DELETE' });
  await ok(res, 'delete');
}
