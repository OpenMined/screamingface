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
import { isAllowedOAuthAuthorizeUrl, isSafeBackendName } from './external-url-policy';

/**
 * In-memory cache of OAuth `state` values per backend/profile.
 *
 * Populated when a launcher run successfully gets an `authorize_url` from
 * `/auth/start`. Read by the manual paste-code IPC path so the renderer
 * can pair the user-pasted authorization code with the correct PKCE state.
 *
 * The entry stays around after the launcher's promise resolves (e.g. on
 * timeout) so the user can still paste the code after the long poll gives
 * up. It is cleared on successful exchange.
 */
const pendingStateByBackendProfile = new Map<string, string>();

function pendingAuthKey(backendName: string, profileName?: string): string {
  return `${backendName}\0${profileName ?? ''}`;
}

export function getPendingAuthState(backendName: string, profileName?: string): string | null {
  return pendingStateByBackendProfile.get(pendingAuthKey(backendName, profileName)) ?? null;
}

export function clearPendingAuthState(backendName: string, profileName?: string): void {
  pendingStateByBackendProfile.delete(pendingAuthKey(backendName, profileName));
}

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
  headers?: Record<string, string>;
}

export async function runOAuthLauncher(opts: LauncherOptions): Promise<LauncherResult> {
  if (!isSafeBackendName(opts.backendName)) {
    return {
      kind: 'failed',
      reason: 'gateway_error',
      message: `invalid browser OAuth backend: ${opts.backendName}`,
    };
  }

  const fetchImpl = opts.fetchImpl ?? fetch;
  const pollIntervalMs = opts.pollIntervalMs ?? 2000;
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1000;
  const query = opts.profileName ? `?name=${encodeURIComponent(opts.profileName)}` : '';
  const startUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/start${query}`;
  const statusUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/status${query}`;

  console.log(`[oauth-launcher] POST ${startUrl}`);
  let startResp: Response;
  try {
    startResp = await fetchImpl(startUrl, { method: 'POST', headers: opts.headers });
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
  const startBody = (await startResp.json()) as { authorize_url?: string; state?: string };
  if (!startBody.authorize_url || !isAllowedOAuthAuthorizeUrl(startBody.authorize_url)) {
    return {
      kind: 'failed',
      reason: 'gateway_error',
      message: 'blocked unexpected OAuth authorize URL',
    };
  }
  if (startBody.state) {
    pendingStateByBackendProfile.set(
      pendingAuthKey(opts.backendName, opts.profileName),
      startBody.state,
    );
  }
  console.log(`[oauth-launcher] opening browser for ${opts.backendName}`);
  await shell.openExternal(startBody.authorize_url);

  const deadline = Date.now() + timeoutMs;
  let networkBlips = 0;
  while (Date.now() < deadline) {
    let statusResp: Response;
    try {
      statusResp = await fetchImpl(statusUrl, { headers: opts.headers });
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
    if (body.state === 'authenticated') {
      clearPendingAuthState(opts.backendName, opts.profileName);
      return { kind: 'complete' };
    }
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
