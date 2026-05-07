/**
 * OAuth launcher — drives the SF auth-proxy flow for aigw-*-backend plugins.
 *
 * Steps:
 *   1. POST <sfBaseUrl>/<backendName>/auth/start to obtain authorize_url.
 *   2. Open authorize_url in the user's default browser via shell.openExternal.
 *   3. Poll <sfBaseUrl>/<backendName>/auth/status until authenticated, error,
 *      or timeout.
 */

import { shell } from 'electron';

export type LauncherResult =
  | { kind: 'complete' }
  | {
      kind: 'failed';
      reason: 'timeout' | 'gateway_error' | 'provider_error' | 'network_error';
      message?: string;
    };

export interface LauncherOptions {
  sfBaseUrl: string;
  backendName: string;
  /**
   * Optional gateway profile name. When set, ?name=<profileName> is appended
   * to both /auth/start and /auth/status URLs so the auth-proxy targets that
   * specific profile. When omitted, the auth-proxy applies its configured
   * default-profile behavior.
   */
  profileName?: string;
  pollIntervalMs?: number;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export async function runOAuthLauncher(opts: LauncherOptions): Promise<LauncherResult> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const pollIntervalMs = opts.pollIntervalMs ?? 2000;
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1000;
  const query = opts.profileName ? `?name=${encodeURIComponent(opts.profileName)}` : '';
  const startUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/start${query}`;
  const statusUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/status${query}`;

  console.log(`[oauth-launcher] POST ${startUrl}`);
  let startResp: Response;
  try {
    startResp = await fetchImpl(startUrl, { method: 'POST' });
  } catch (e) {
    console.log(`[oauth-launcher] start fetch threw:`, e);
    return { kind: 'failed', reason: 'network_error', message: String(e) };
  }
  console.log(`[oauth-launcher] start status=${startResp.status}`);
  if (!startResp.ok) {
    let body = '';
    try {
      body = await startResp.text();
    } catch {
      /* ignore */
    }
    console.log(`[oauth-launcher] start body=${body.slice(0, 500)}`);
    return {
      kind: 'failed',
      reason: 'gateway_error',
      message: `start returned ${startResp.status}: ${body.slice(0, 200)}`,
    };
  }
  const startBody = (await startResp.json()) as { authorize_url: string };
  console.log(`[oauth-launcher] opening browser: ${startBody.authorize_url}`);
  await shell.openExternal(startBody.authorize_url);

  const deadline = Date.now() + timeoutMs;
  let networkBlips = 0;
  while (Date.now() < deadline) {
    let statusResp: Response;
    try {
      statusResp = await fetchImpl(statusUrl);
    } catch {
      networkBlips += 1;
      if (networkBlips >= 5) {
        return { kind: 'failed', reason: 'network_error' };
      }
      await sleep(pollIntervalMs);
      continue;
    }
    networkBlips = 0;
    if (statusResp.status === 404) {
      return { kind: 'failed', reason: 'gateway_error', message: 'profile not found' };
    }
    if (!statusResp.ok) {
      return {
        kind: 'failed',
        reason: 'gateway_error',
        message: `status returned ${statusResp.status}`,
      };
    }
    const body = (await statusResp.json()) as { state: string; error?: string };
    if (body.state === 'authenticated') return { kind: 'complete' };
    if (body.state === 'error') {
      return { kind: 'failed', reason: 'provider_error', message: body.error };
    }
    await sleep(pollIntervalMs);
  }
  return { kind: 'failed', reason: 'timeout' };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
