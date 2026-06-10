// apps/desktop/src/renderer/src/lib/url4-format.ts
//
// Calls the server's POST /ensemble/format to pretty-print a url4 expression.
// Returns the formatted string, or null on any failure (caller keeps the
// original text). POST (not GET) so large expressions aren't URL-length capped.

export async function formatUrl4(serverUrl: string, expression: string): Promise<string | null> {
  if (!serverUrl) return null;
  try {
    const res = await window.electronAPI.server.fetch(`${serverUrl}/ensemble/format`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: expression }),
    });
    if (!res.ok) return null;
    const data = JSON.parse(res.body) as { formatted?: string; error?: string | null };
    if (data.error || typeof data.formatted !== 'string') return null;
    return data.formatted;
  } catch {
    return null;
  }
}
