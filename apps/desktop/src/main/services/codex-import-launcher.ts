export type ImportProfileResult = { ok: true } | { ok: false; status?: number; message?: string };

export interface ImportProfileOptions {
  sfBaseUrl: string;
  backendName: string;
  profileName?: string;
  fetchImpl?: typeof fetch;
}

export async function runImportProfile(opts: ImportProfileOptions): Promise<ImportProfileResult> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const query = opts.profileName ? `?name=${encodeURIComponent(opts.profileName)}` : '';
  const url = `${opts.sfBaseUrl}/${opts.backendName}/auth/import${query}`;
  try {
    const resp = await fetchImpl(url, { method: 'POST' });
    if (resp.ok) return { ok: true };
    let message: string | undefined;
    try {
      const body = (await resp.json()) as { detail?: { code?: string; message?: string } };
      message = body.detail?.message ?? body.detail?.code;
    } catch {
      /* ignore */
    }
    return { ok: false, status: resp.status, message };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}
